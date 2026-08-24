"""Auth API: login / logout / me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Config
from app.models import User
from app.passwords import verify_password
from backend.deps import get_current_user, get_db
from backend.schemas.auth import LoginBody, UserOut
from backend.security import create_access_token

router = APIRouter()


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=Config.COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=Config.COOKIE_SECURE,
        max_age=Config.JWT_EXPIRE_HOURS * 3600,
        path="/",
    )


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        school_id=user.school_id,
        school_name=user.school.name if user.school else None,
    )


@router.post("/login", response_model=UserOut)
def login(
    body: LoginBody, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    email = body.email.lower().strip()
    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    token = create_access_token(
        user_id=user.id, role=user.role, school_id=user.school_id
    )
    _set_session_cookie(response, token)
    return _user_out(user)


@router.post("/logout", status_code=204, response_class=Response)
def logout(response: Response) -> Response:
    response.delete_cookie(Config.COOKIE_NAME, path="/")
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(user)
