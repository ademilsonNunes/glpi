from __future__ import annotations
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext

SECRET_KEY = os.getenv("AUTH_SECRET", "change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_TTL_MIN", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

DEFAULT_USER = os.getenv("AUTH_USER", "admin")
DEFAULT_PLAIN = os.getenv("AUTH_PASSWORD", "admin123")
DEFAULT_HASH = os.getenv("AUTH_HASH", "")

LOGIN_WINDOW_SEC = int(os.getenv("AUTH_LOGIN_WINDOW_SEC", "60"))
LOGIN_MAX_ATTEMPTS = int(os.getenv("AUTH_LOGIN_MAX_ATTEMPTS", "12"))
_LOGIN_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def authenticate_user(username: str, password: str) -> bool:
    if username != DEFAULT_USER:
        return False
    if DEFAULT_HASH:
        return verify_password(password, DEFAULT_HASH)
    return password == DEFAULT_PLAIN


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Nao autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "").strip()
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _enforce_login_rate_limit(request: Request) -> None:
    if LOGIN_MAX_ATTEMPTS <= 0:
        return
    ip = _client_ip(request)
    now = time.monotonic()
    bucket = _LOGIN_ATTEMPTS[ip]
    while bucket and now - bucket[0] > LOGIN_WINDOW_SEC:
        bucket.popleft()
    if len(bucket) >= LOGIN_MAX_ATTEMPTS:
        retry_after = max(1, int(LOGIN_WINDOW_SEC - (now - bucket[0])))
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas de login. Tente novamente em instantes.",
            headers={"Retry-After": str(retry_after)},
        )
    bucket.append(now)


def login_handler(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    _enforce_login_rate_limit(request)
    if not authenticate_user(form_data.username, form_data.password):
        raise HTTPException(status_code=400, detail="Usuario ou senha invalidos")
    token = create_access_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer"}
