# backend/auth/auth.py
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings

ph = PasswordHasher()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return ph.verify(hashed_password, password)
    except VerifyMismatchError:
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.jwt_access_exp_minutes)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except (JWTError, ValueError):
        return None


def verify_token(token: str) -> dict[str, Any] | None:
    """Verify token and return full payload if valid."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload
    except (JWTError, ValueError):
        return None


def _hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def create_refresh_token(
    user_id: int,
    db: AsyncSession,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> str:
    from backend.db.models import UserSession

    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_refresh_token(raw_token)
    expires_at = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_exp_days)

    session = UserSession(
        user_id=user_id,
        refresh_token_hash=token_hash,
        expires_at=expires_at,
        revoked=False,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(session)
    await db.flush()
    return raw_token


async def verify_and_rotate_refresh_token(
    raw_token: str,
    db: AsyncSession,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[int, str] | None:
    """Find session by hash, check validity, rotate (revoke old, create new).

    Returns (user_id, new_raw_refresh_token) on success, None on failure.
    """
    from backend.db.models import UserSession

    token_hash = _hash_refresh_token(raw_token)
    now = datetime.now(UTC)

    result = await db.execute(
        select(UserSession).where(
            UserSession.refresh_token_hash == token_hash,
            UserSession.revoked.is_(False),
            UserSession.expires_at > now,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None

    user_id = session.user_id

    # Revoke old session
    session.revoked = True
    await db.flush()

    # Create rotated session
    new_raw = secrets.token_urlsafe(48)
    new_hash = _hash_refresh_token(new_raw)
    new_expires = now + timedelta(days=settings.jwt_refresh_exp_days)
    new_session = UserSession(
        user_id=user_id,
        refresh_token_hash=new_hash,
        expires_at=new_expires,
        revoked=False,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(new_session)
    await db.flush()

    return user_id, new_raw


async def revoke_refresh_token(raw_token: str, db: AsyncSession) -> None:
    from backend.db.models import UserSession

    token_hash = _hash_refresh_token(raw_token)
    result = await db.execute(
        select(UserSession).where(UserSession.refresh_token_hash == token_hash)
    )
    session = result.scalar_one_or_none()
    if session:
        session.revoked = True
        await db.flush()
