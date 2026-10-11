"""Authentication and Audit Log API Endpoints (Part 15)."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import User, UserRole, AuditLog
from app.schemas.auth import UserRegister, UserCreate, UserLogin, Token, UserResponse
from app.auth.utils import verify_password, create_access_token
from app.auth.dependencies import get_current_user, require_role
from app.services.user_service import create_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    """Register a new user account with role (public self-service registration)."""
    requested_role = (payload.role or UserRole.HOSPITAL_STAFF).strip().upper()
    if requested_role != UserRole.HOSPITAL_STAFF:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration can only create HOSPITAL_STAFF accounts. Contact an administrator for other roles.",
        )

    try:
        user = create_user(
            db=db,
            email=payload.email,
            password=payload.password,
            role=UserRole.HOSPITAL_STAFF,
        )
        return user
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user_by_admin(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Admin-only endpoint to create users with any authorization role."""
    try:
        user = create_user(
            db=db,
            email=payload.email,
            password=payload.password,
            role=payload.role,
        )
        return user
    except ValueError as exc:
        # Check if error is due to invalid role or duplicate email
        err_msg = str(exc)
        if "Invalid role" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err_msg,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """Authenticate credentials and generate JWT access token."""
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(data={"sub": str(user.id), "email": user.email, "role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "user_id": user.id,
    }


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Retrieve profile of currently authenticated user."""
    return current_user


@router.get("/audit-logs")
def list_audit_logs(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Retrieve recent security audit log entries (ADMIN only)."""
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "user_id": l.user_id,
            "action": l.action,
            "resource": l.resource,
            "resource_id": l.resource_id,
            "timestamp": l.timestamp.isoformat(),
            "details": l.details,
        }
        for l in logs
    ]
