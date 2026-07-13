from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Cookie, Depends, Header, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.core.database.session import Session, get_db
from backend.modules.identity.models import ApiKey, User, UserRole
from backend.modules.identity.service import decode_token
from backend.modules.organizations.models import Organization
from backend.observability.context import bind_log_context

logger = logging.getLogger(__name__)


@dataclass
class OrgUser:
    user: User
    org_id: int | None


async def _touch_api_key_last_used(key_id: int) -> None:
    """Best-effort last_used_at update in its own transaction.

    Avoids holding row locks on the request session when downstream handlers
    block (e.g. orchestrator init bugs or long-running dispatch).
    """
    try:
        async with Session() as db:
            await db.execute(
                update(ApiKey)
                .where(ApiKey.id == key_id)
                .values(last_used_at=datetime.now(UTC))
            )
            await db.commit()
    except Exception:
        logger.debug("Failed to update api_key.last_used_at for id=%s", key_id, exc_info=True)


async def get_user_from_token(token: str, db: AsyncSession) -> User | None:
    user_id = decode_token(token)
    if not user_id:
        return None
    q = await db.execute(select(User).where(User.id == user_id))
    return q.scalar_one_or_none()


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


async def _resolve_api_key(authorization: str, db: AsyncSession) -> User | None:
    """
    Attempt to authenticate via an API key in the Authorization header.

    Key format: Bearer sk-{8-hex-prefix}_{32-hex-secret}

    Returns the org-owner User on success, None if the header is not an API
    key (so the caller can fall through to JWT logic), or raises HTTPException
    if the key format matches but authentication fails.
    """
    if not authorization.startswith("Bearer sk-"):
        return None

    raw = authorization.split(" ", 1)[1].strip()  # sk-{prefix}_{secret}
    # Strip the "sk-" prefix and split on the first underscore
    remainder = raw[3:]  # "{prefix}_{secret}"
    if "_" not in remainder:
        raise HTTPException(status_code=401, detail="Invalid API key format")

    prefix, secret = remainder.split("_", 1)
    if not prefix or not secret:
        raise HTTPException(status_code=401, detail="Invalid API key format")

    key_hash = hashlib.sha256(secret.encode()).hexdigest()

    q = await db.execute(
        select(ApiKey).where(
            ApiKey.key_prefix == prefix,
            ApiKey.revoked == False,  # noqa: E712
        )
    )
    api_key = q.scalar_one_or_none()

    if api_key is None or api_key.key_hash != key_hash:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if api_key.expires_at and api_key.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=401, detail="API key expired")

    asyncio.create_task(_touch_api_key_last_used(int(api_key.id)))

    # Resolve the org owner as the auth identity for this key
    if api_key.org_id is None:
        raise HTTPException(status_code=401, detail="API key has no associated organisation")

    org = await db.get(Organization, api_key.org_id)
    if org is None:
        raise HTTPException(status_code=401, detail="Organisation not found")

    user_q = await db.execute(select(User).where(User.id == org.owner_id))
    user = user_q.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Organisation owner not found")

    return user


async def resolve_user_from_request(
    *,
    db: AsyncSession,
    authorization: str | None = None,
    access_token: str | None = None,
    query_token: str | None = None,
    include_query_token: bool = False,
) -> User:
    # --- API key path (Bearer sk-...) ---
    # Must be checked before the generic JWT bearer path so the format-specific
    # error messages are returned correctly. Returns None if the header is not
    # an API key, raises HTTPException if it is an API key but auth fails.
    if authorization and authorization.startswith("Bearer sk-"):
        user = await _resolve_api_key(authorization, db)
        if user is not None:
            return user

    # --- JWT / cookie path ---
    token_candidates: list[tuple[str, str]] = []
    bearer = _bearer_token(authorization)
    if bearer and not bearer.startswith("sk-"):
        # Frontend session_present marker is "1" — not a JWT.
        if bearer != "1":
            token_candidates.append(("authorization", bearer))
    if access_token:
        token_candidates.append(("cookie", access_token))
    if include_query_token and query_token:
        token_candidates.append(("query", query_token))

    if not token_candidates:
        raise HTTPException(status_code=401, detail="Missing token")

    for source, token in token_candidates:
        user = await get_user_from_token(token, db)
        if user is not None:
            return user
        logger.warning("Rejected auth token from %s source", source)

    raise HTTPException(status_code=401, detail="Invalid token")


async def require_user(
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await resolve_user_from_request(
        db=db,
        authorization=authorization,
        access_token=access_token,
    )
    bind_log_context(org_id=user.org_id, user_id=user.id)
    return user


async def require_user_header_or_query(
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Require auth from Authorization header, cookie, or `?token=` query param.
    Useful for endpoints accessed by <img> or other clients without headers.
    """
    return await resolve_user_from_request(
        db=db,
        authorization=authorization,
        access_token=access_token,
        query_token=token,
        include_query_token=True,
    )


def _split_list(value: str) -> set[str]:
    if not value:
        return set()
    parts = []
    for chunk in value.replace(",", " ").split():
        if chunk:
            parts.append(chunk.strip().lower())
    return set(parts)


async def require_org_user(
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> OrgUser:
    user = await require_user(authorization=authorization, access_token=access_token, db=db)
    return OrgUser(user=user, org_id=user.org_id)


ORG_WRITE_ROLES = {UserRole.org_admin, UserRole.ops_manager, UserRole.admin}
MISSION_EXEC_ROLES = {
    UserRole.org_admin,
    UserRole.ops_manager,
    UserRole.pilot,
    UserRole.admin,
    UserRole.operator,
}


async def require_org_write(org_user: OrgUser = Depends(require_org_user)) -> OrgUser:
    if org_user.user.role not in ORG_WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return org_user


async def require_mission_exec(org_user: OrgUser = Depends(require_org_user)) -> OrgUser:
    if org_user.user.role not in MISSION_EXEC_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return org_user


async def require_admin(
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await require_user(authorization=authorization, access_token=access_token, db=db)

    # Primary: role-based check
    if user.role == UserRole.admin:
        return user

    # Transitional fallback: email/domain match (kept for P1 compatibility; remove in P2)
    admin_emails = _split_list(settings.admin_emails)
    admin_domains = _split_list(settings.admin_domains)

    email = (user.email or "").lower()
    domain = email.split("@", 1)[1] if "@" in email else ""

    if (admin_emails and email in admin_emails) or (admin_domains and domain in admin_domains):
        logger.warning(
            "Admin access granted via email/domain fallback for user %s — "
            "set role=admin in DB and remove admin_emails/admin_domains config in P2.",
            user.email,
        )
        return user

    raise HTTPException(status_code=403, detail="Admin privileges required")


def require_roles(*allowed_roles: UserRole):
    allowed = set(allowed_roles)

    async def _require(org_user: OrgUser = Depends(require_org_user)) -> OrgUser:
        if org_user.user.role == UserRole.admin:
            return org_user
        if org_user.user.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return org_user

    return _require
