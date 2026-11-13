from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import User, now
from ..security import create_token, current_user, hash_password, verify_password
from ..services import quota

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)
    nickname: str = Field(default="", max_length=32)
    privacyConsent: bool = False


class LoginIn(BaseModel):
    email: str
    password: str


def _user_out(db: Session, u: User) -> dict:
    return {"id": u.id, "email": u.email, "nickname": u.nickname or u.email.split("@")[0], "isAdmin": u.is_admin,
            "quota": quota.status(db, u)}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "邮箱格式不正确")
    if not body.privacyConsent:
        raise HTTPException(400, "请先阅读并同意隐私与照片授权说明")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "该邮箱已注册")
    admins = {e.strip().lower() for e in settings.admin_emails.split(",")}
    u = User(email=email, password_hash=hash_password(body.password), nickname=body.nickname,
             is_admin=email in admins, privacy_consent_at=now())
    db.add(u)
    db.commit()
    return {"token": create_token(u.id), "user": _user_out(db, u)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "邮箱或密码错误")
    return {"token": create_token(u.id), "user": _user_out(db, u)}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _user_out(db, user)
