# backend/routes_auth.py
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional

from backend.db.session import Session
from backend.db.models import User
from backend.auth.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---- DB dependency (matches your session.py) ----
async def get_db() -> AsyncSession:
    async with Session() as s:
        yield s


# ---- Schemas ----
class SignUpIn(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class AuthOut(BaseModel):
    access_token: str
    user: UserOut


# ---- Helpers ----
async def get_current_user(
    db: AsyncSession,
    authorization: Optional[str],
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1].strip()
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    q = await db.execute(select(User).where(User.id == user_id))
    user = q.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ---- Routes ----
@router.post("/signup", response_model=AuthOut)
async def signup(payload: SignUpIn, db: AsyncSession = Depends(get_db)):
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
    await db.flush()  # so user.id exists
    await db.commit()

    token = create_access_token(user.id)
    return {"access_token": token, "user": user}


@router.post("/login", response_model=AuthOut)
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)):
    email = payload.email.lower().strip()

    q = await db.execute(select(User).where(User.email == email))
    user = q.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user.id)
    return {"access_token": token, "user": user}


@router.get("/me", response_model=UserOut)
async def me(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(db, authorization)
    return user
