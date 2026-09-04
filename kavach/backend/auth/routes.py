"""routes.py — FastAPI authentication endpoints (register, login, logout, me) and dependencies."""

from typing import Optional
import uuid

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.auth.security import (
    JWT_EXPIRATION_DAYS,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.db.models import User
from backend.db.session import get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    created_at: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Auth Dependencies
# ---------------------------------------------------------------------------

def get_current_user(
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """Extracts and validates the current user from the httpOnly cookie or Authorization header."""
    token = access_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. No session cookie or token provided.",
        )

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )

    user_id = payload["sub"]
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed user identity.")

    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account not found.")

    return user


def get_optional_user(
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Returns the authenticated user if present, or None if unauthenticated."""
    try:
        return get_current_user(access_token=access_token, authorization=authorization, db=db)
    except HTTPException:
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """Registers a new user account, returning 409 Conflict if email already exists."""
    email_clean = req.email.strip().lower()
    if not email_clean or not req.password:
        raise HTTPException(status_code=400, detail="Email and password cannot be blank.")

    existing = db.query(User).filter(User.email == email_clean).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{email_clean}' already exists.",
        )

    pwd_hash = hash_password(req.password)
    user = User(
        name=req.name.strip() or email_clean.split("@")[0],
        email=email_clean,
        password_hash=pwd_hash,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse(
        id=str(user.id),
        name=user.name,
        email=user.email,
        created_at=user.created_at.isoformat(),
    )


@router.post("/login", response_model=UserResponse)
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Authenticates user credentials and sets an httpOnly session cookie with SameSite=Lax."""
    email_clean = req.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token({"sub": str(user.id), "email": user.email, "name": user.name})
    max_age = JWT_EXPIRATION_DAYS * 24 * 3600

    response.set_cookie(
        key="access_token",
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True when SSL/HTTPS is deployed
        path="/",
    )

    return UserResponse(
        id=str(user.id),
        name=user.name,
        email=user.email,
        created_at=user.created_at.isoformat(),
    )


@router.post("/logout")
def logout(response: Response):
    """Clears the session cookie."""
    response.delete_cookie(key="access_token", path="/")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    """Returns the authenticated user profile."""
    return UserResponse(
        id=str(current_user.id),
        name=current_user.name,
        email=current_user.email,
        created_at=current_user.created_at.isoformat(),
    )
