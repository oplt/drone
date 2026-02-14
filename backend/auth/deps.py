from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.auth import decode_token
from backend.config import settings
from backend.db.models import User
from backend.db.session import get_db


async def get_user_from_token(
    token: str, db: AsyncSession
) -> Optional[User]:
    user_id = decode_token(token)
    if not user_id:
        return None
    q = await db.execute(select(User).where(User.id == user_id))
    return q.scalar_one_or_none()


async def require_user(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token = authorization.split(" ", 1)[1].strip()
    user = await get_user_from_token(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


async def require_user_header_or_query(
    token: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Require auth from Authorization header or `?token=` query param.
    Useful for endpoints accessed by <img> or other clients without headers.
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()

    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    user = await get_user_from_token(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def _split_list(value: str) -> set[str]:
    if not value:
        return set()
    # Split on commas and whitespace
    parts = []
    for chunk in value.replace(",", " ").split():
        if chunk:
            parts.append(chunk.strip().lower())
    return set(parts)


async def require_admin(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await require_user(authorization=authorization, db=db)

    admin_emails = _split_list(settings.admin_emails)
    admin_domains = _split_list(settings.admin_domains)

    email = (user.email or "").lower()
    domain = email.split("@", 1)[1] if "@" in email else ""

    if (admin_emails and email in admin_emails) or (
        admin_domains and domain in admin_domains
    ):
        return user

    raise HTTPException(status_code=403, detail="Admin privileges required")
