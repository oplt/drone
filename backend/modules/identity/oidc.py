from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class OIDCUserInfo:
    sub: str
    email: str
    name: str | None
    picture: str | None


class GoogleOIDCProvider:
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

    def authorization_url(self, state: str) -> str:
        from urllib.parse import urlencode

        from backend.core.config.runtime import settings

        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_oidc_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> OIDCUserInfo:
        from backend.core.config.runtime import settings

        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                self.TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_oidc_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            info_resp = await client.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            info_resp.raise_for_status()
            data = info_resp.json()

        return OIDCUserInfo(
            sub=data["sub"],
            email=data["email"],
            name=data.get("name"),
            picture=data.get("picture"),
        )


google_oidc = GoogleOIDCProvider()


async def get_or_create_sso_user(db: AsyncSession, info: OIDCUserInfo):
    import secrets

    from backend.modules.identity.models import User, UserRole
    from backend.modules.identity.service import hash_password

    q = await db.execute(select(User).where(User.email == info.email.lower()))
    user = q.scalar_one_or_none()
    if user is None:
        user = User(
            email=info.email.lower(),
            hashed_password=hash_password(secrets.token_hex(32)),
            full_name=info.name,
            role=UserRole.pilot,
        )
        db.add(user)
        await db.flush()
    return user
