"""Create users — main admin only. No co-admin role."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import require_main_admin
from app.core.security import get_password_hash
from app.database import get_db
from app.models import MonitoringSetting, User, UserRole
from app.schemas import UserAdminUpdate, UserCreate, UserResponse
from app.services.monitoring_user import get_user_monitoring

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/", response_model=list[UserResponse])
@router.get("", response_model=list[UserResponse], include_in_schema=False)
def list_users(db: Session = Depends(get_db), _: User = Depends(require_main_admin)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_main_admin),
):
    email = data.email.strip().lower()
    if db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=email,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name.strip(),
        role=UserRole.USER,
        is_primary=False,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    get_user_monitoring(db, user.id)
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    data: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_main_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_primary:
        if data.is_active is not None and not data.is_active:
            raise HTTPException(status_code=400, detail="Primary administrator cannot be deactivated")

    if data.email is not None:
        new_email = data.email.strip().lower()
        existing = db.query(User).filter(func.lower(User.email) == new_email, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = new_email

    if data.full_name is not None:
        user.full_name = data.full_name.strip()

    if data.is_active is not None:
        if user.id == current_user.id and not data.is_active:
            raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
        user.is_active = data.is_active

    if data.password:
        user.hashed_password = get_password_hash(data.password)

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_main_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_primary:
        raise HTTPException(status_code=400, detail="Primary administrator cannot be deleted")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    db.delete(user)
    db.commit()
    return {"message": "User deleted"}
