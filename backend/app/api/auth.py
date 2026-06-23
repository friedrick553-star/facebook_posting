from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.exc import OperationalError, TimeoutError as SATimeoutError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.db_ready import require_db_ready
from app.core.deps import get_current_user
from app.core.security import create_access_token, get_password_hash, verify_password
from app.database import get_db
from app.models import User
from app.schemas import (
    AdminSetupRequest,
    ForgotPasswordRequest,
    LoginRequest,
    PasswordChangeRequest,
    SetupStatusResponse,
    Token,
    UserResponse,
    UserUpdate,
)
from app.seeds.seed_data import seed_database
from app.services.admin_setup import is_admin_setup_needed, persist_admin_env, reload_settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@router.get("/setup-status", response_model=SetupStatusResponse)
def setup_status(
    _: None = Depends(require_db_ready),
    db: Session = Depends(get_db),
):
    return SetupStatusResponse(needs_setup=is_admin_setup_needed(db))


@router.post("/setup")
def complete_setup(
    data: AdminSetupRequest,
    _: None = Depends(require_db_ready),
    db: Session = Depends(get_db),
):
    if not is_admin_setup_needed(db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin already configured")

    email = _normalize_email(str(data.email))
    try:
        if db.query(User).filter(func.lower(User.email) == email).first():
            raise HTTPException(status_code=400, detail="Email already in use")
    except (OperationalError, SATimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database busy — wait a moment and try again.",
        ) from exc

    persist_admin_env(email, data.password)
    reload_settings()
    seed_database(db, email, data.password)
    return {"message": "Admin configured successfully"}


@router.post("/login", response_model=Token)
def login(
    data: LoginRequest,
    request: Request,
    _: None = Depends(require_db_ready),
    db: Session = Depends(get_db),
):
    email = _normalize_email(str(data.email))
    try:
        user = db.query(User).filter(func.lower(User.email) == email).first()
    except (OperationalError, SATimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database busy — wait a moment and try again.",
        ) from exc

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    token = create_access_token({"sub": user.email, "role": user.role.value})
    return Token(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/profile", response_model=UserResponse)
def update_profile(data: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if data.full_name:
        current_user.full_name = data.full_name
    if data.email and _normalize_email(str(data.email)) != _normalize_email(current_user.email):
        new_email = _normalize_email(str(data.email))
        if db.query(User).filter(func.lower(User.email) == new_email).first():
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = new_email
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/change-password")
def change_password(
    data: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.hashed_password = get_password_hash(data.new_password)
    db.commit()
    return {"message": "Password updated successfully"}


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = _normalize_email(str(data.email))
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user:
        return {
            "message": "If an account exists with this email, password reset instructions have been sent.",
            "note": "Contact your administrator to reset your password.",
        }
    return {"message": "If an account exists with this email, password reset instructions have been sent."}
