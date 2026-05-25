# backend/routes_auth.py

import logging
import secrets as _secrets

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.core.database.session import Session
from backend.modules.identity.models import AuthAuditLog, User
from backend.modules.identity.service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    revoke_refresh_token,
    verify_and_rotate_refresh_token,
    verify_password,
)
from backend.modules.organizations.models import Organization
from backend.modules.organizations.service import ensure_user_workspace, get_default_project

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---- DB dependency ----
async def get_db() -> AsyncSession:
    async with Session() as s:
        yield s


# ---- Schemas ----
class SignUpIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class UserOut(BaseModel):
    id: int
    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    role: str = "operator"
    org_id: int | None = None
    org_name: str | None = None
    org_slug: str | None = None
    default_project_id: int | None = None
    default_project_name: str | None = None
    default_project_slug: str | None = None


class AuthOut(BaseModel):
    user: UserOut


# ---- Helpers ----
async def _write_audit(
    db: AsyncSession,
    *,
    user_id: int | None,
    org_id: int | None,
    event: str,
    request: Request,
) -> None:
    db.add(
        AuthAuditLog(
            user_id=user_id,
            org_id=org_id,
            event=event,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )


def _set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    *,
    remember_me: bool = True,
) -> None:
    refresh_max_age = settings.jwt_refresh_exp_days * 24 * 3600 if remember_me else None
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.jwt_access_exp_minutes * 60,
        path="/",
        domain=settings.cookie_domain or None,
    )
    response.set_cookie(
        "auth_remembered",
        "1" if remember_me else "0",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=refresh_max_age,
        path="/auth",
        domain=settings.cookie_domain or None,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=refresh_max_age,
        path="/auth",
        domain=settings.cookie_domain or None,
    )
    response.set_cookie(
        "session_present",
        "1",
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=refresh_max_age,
        path="/",
        domain=settings.cookie_domain or None,
    )


def _clear_auth_cookies(response: Response) -> None:
    cookie_domain = settings.cookie_domain or None
    response.delete_cookie("access_token", path="/", domain=cookie_domain)
    response.delete_cookie("refresh_token", path="/auth", domain=cookie_domain)
    response.delete_cookie("auth_remembered", path="/auth", domain=cookie_domain)
    response.delete_cookie("session_present", path="/", domain=cookie_domain)


async def get_current_user(
    db: AsyncSession,
    authorization: str | None,
    access_token_cookie: str | None = None,
) -> User:
    candidate_tokens = []
    if authorization and authorization.startswith("Bearer "):
        candidate_tokens.append(authorization.split(" ", 1)[1].strip())
    if access_token_cookie:
        candidate_tokens.append(access_token_cookie)

    if not candidate_tokens:
        raise HTTPException(status_code=401, detail="Missing token")

    user = None
    for token in candidate_tokens:
        user_id = decode_token(token)
        if not user_id:
            continue
        q = await db.execute(select(User).where(User.id == user_id))
        user = q.scalar_one_or_none()
        if user is not None:
            break
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def _user_out(db: AsyncSession, user: User) -> dict:
    org = await db.get(Organization, user.org_id) if user.org_id else None
    default_project = await get_default_project(db, org_id=user.org_id) if user.org_id else None
    return {
        "id": user.id,
        "email": user.email,
        "first_name": None,
        "last_name": None,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "org_id": user.org_id,
        "org_name": org.name if org else None,
        "org_slug": org.slug if org else None,
        "default_project_id": default_project.id if default_project else None,
        "default_project_name": default_project.name if default_project else None,
        "default_project_slug": default_project.slug if default_project else None,
    }


# ---- Routes ----
@router.post("/signup", response_model=AuthOut)
async def signup(
    payload: SignUpIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    email = payload.email.lower().strip()

    q = await db.execute(select(User).where(User.email == email))
    if q.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password too short (min 8 chars).")
    if len(payload.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password too long (max 72 bytes).")

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    await db.flush()
    await ensure_user_workspace(db, user=user)

    access_token = create_access_token(user.id)
    refresh_token = await create_refresh_token(
        user.id,
        db,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    await _write_audit(db, user_id=user.id, org_id=user.org_id, event="signup", request=request)
    await db.commit()

    _set_auth_cookies(response, access_token, refresh_token, remember_me=True)
    return {"user": await _user_out(db, user)}


@router.post("/login", response_model=AuthOut)
async def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    email = payload.email.lower().strip()

    q = await db.execute(select(User).where(User.email == email))
    user = q.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        async with Session() as audit_db:
            await _write_audit(
                audit_db, user_id=None, org_id=None, event="login_failed", request=request
            )
            await audit_db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    await ensure_user_workspace(db, user=user)

    access_token = create_access_token(user.id)
    refresh_token = await create_refresh_token(
        user.id,
        db,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    await _write_audit(
        db, user_id=user.id, org_id=user.org_id, event="login_success", request=request
    )
    await db.commit()

    _set_auth_cookies(response, access_token, refresh_token, remember_me=payload.remember_me)
    return {"user": await _user_out(db, user)}


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    auth_remembered: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    result = await verify_and_rotate_refresh_token(
        refresh_token,
        db,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    if result is None:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user_id, new_refresh_token = result
    new_access_token = create_access_token(user_id)
    await db.commit()

    _set_auth_cookies(
        response,
        new_access_token,
        new_refresh_token,
        remember_me=auth_remembered == "1",
    )
    return {"ok": True}


@router.post("/logout")
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    if refresh_token:
        await revoke_refresh_token(refresh_token, db)
        await db.commit()
    _clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(db, authorization, access_token)
    await ensure_user_workspace(db, user=user)
    await db.commit()
    return await _user_out(db, user)


@router.get("/oidc/google")
async def oidc_google_start():
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google OIDC not configured")
    from backend.modules.identity.oidc import google_oidc

    state = _secrets.token_urlsafe(16)
    url = google_oidc.authorization_url(state=state)
    return RedirectResponse(url)


@router.get("/oidc/google/callback")
async def oidc_google_callback(
    code: str,
    state: str,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google OIDC not configured")
    from backend.modules.identity.oidc import get_or_create_sso_user, google_oidc

    try:
        info = await google_oidc.exchange_code(code)
    except Exception as exc:
        logger.warning("OIDC exchange failed: %s", exc)
        raise HTTPException(status_code=400, detail="OIDC exchange failed")

    user = await get_or_create_sso_user(db, info)
    await ensure_user_workspace(db, user=user)
    access_token = create_access_token(user.id)
    refresh_token = await create_refresh_token(
        user.id,
        db,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    await _write_audit(
        db,
        user_id=user.id,
        org_id=user.org_id,
        event="login_success_oidc",
        request=request,
    )
    await db.commit()
    _set_auth_cookies(response, access_token, refresh_token, remember_me=True)
    return RedirectResponse("/dashboard")
