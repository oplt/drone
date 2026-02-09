# backend/auth/auth.py
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from typing import Optional

ph = PasswordHasher()

JWT_SECRET = "CHANGE_ME_USE_ENV"
JWT_ALG = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return ph.verify(hashed_password, password)
    except VerifyMismatchError:
        return False

def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def decode_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except (JWTError, ValueError):
        return None
