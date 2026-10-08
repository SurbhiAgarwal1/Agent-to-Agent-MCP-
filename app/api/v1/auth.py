"""Authentication and Audit Log API Endpoints (Part 15)."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.auth.models import User, UserRole, AuditLog
from app.auth.schemas import UserRegister, UserLogin, Token, UserResponse
from app.auth.utils import hash_password, verify_password, create_access_token
from app.auth.dependencies import get_current_user, require_role

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    """Register a new user account with role."""
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )

    role = payload.role.strip().upper()
    if role not in UserRole.ALL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{payload.role}'. Must be one of: {UserRole.ALL_ROLES}",
        )

    hashed_pw = hash_password(payload.password)
    user = User(
        email=payload.email,
        hashed_password=hashed_pw,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


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
    current_user: User = Depends(get_current_user),
):
    """Retrieve recent security audit log entries (authenticated)."""
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
