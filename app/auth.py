import os
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, UserRole

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-please")


def refresh_secret_key() -> str:
    """Перечитать SECRET_KEY после load_dotenv() — иначе cookie-сессии «ломаются»."""
    global SECRET_KEY
    SECRET_KEY = (os.getenv("SECRET_KEY") or SECRET_KEY or "change-me-in-production-please").strip()
    return SECRET_KEY


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    if user.role == UserRole.manager and not user.is_approved:
        return None
    return user


def find_user(db: Session, username: str, password: str) -> tuple[Optional[User], Optional[str]]:
    """Returns (user, error_key). error_key: wrong_credentials | pending_approval"""
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return None, "wrong_credentials"
    if user.role == UserRole.manager and not user.is_approved:
        return user, "pending_approval"
    return user, None


def wants_json(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept and "text/html" not in accept:
        return True
    if (request.headers.get("x-requested-with") or "").lower() == "xmlhttprequest":
        return True
    path = request.url.path or ""
    return path.startswith("/api/")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Без сессии:
      - API/JSON → 401 JSON
      - браузер  → 401 с headers, exception handler сделает redirect на /login
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не авторизован",
            headers={"X-Auth-Redirect": "/login"},
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
            headers={"X-Auth-Redirect": "/login"},
        )
    if user.role == UserRole.manager and not user.is_approved:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт ещё не одобрен администратором",
            headers={"X-Auth-Redirect": "/login?pending=1"},
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только для администратора")
    return user


def can_access_recording(user: User, recording_user_id: int) -> bool:
    if user.role == UserRole.admin:
        return True
    return user.id == recording_user_id
