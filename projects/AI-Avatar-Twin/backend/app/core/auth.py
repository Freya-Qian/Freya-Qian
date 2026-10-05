"""鉴权：本地验证码 + 不透明 token（内部试用；上线前接真实短信）。"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.config import settings
from app.core.db import get_db
from app.core.llm import LLMError
from app.models import AuthToken, User

CODE_TTL = timedelta(minutes=5)


def generate_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def issue_token(db: Session, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthToken(
        token=token,
        user_id=user_id,
        expires_at=datetime.now() + timedelta(days=settings.token_ttl_days),
    ))
    db.commit()
    return token


def revoke_token(db: Session, token: str) -> None:
    row = db.get(AuthToken, token)
    if row:
        db.delete(row)
        db.commit()


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise LLMError("UNAUTHORIZED", "未登录或登录已过期")
    token = authorization[len("Bearer "):].strip()
    row = db.get(AuthToken, token)
    if not row or row.expires_at < datetime.now():
        raise LLMError("UNAUTHORIZED", "未登录或登录已过期")
    user = db.get(User, row.user_id)
    if not user:
        raise LLMError("UNAUTHORIZED", "用户不存在")
    return user
