"""User creation service providing reusable account registration logic."""

from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import User, UserRole
from app.auth.utils import hash_password


def create_user(
    db: Session,
    email: str,
    password: str,
    role: str = UserRole.HOSPITAL_STAFF,
) -> User:
    """Create a new user account with validated role and hashed password.
    
    Args:
        db: Active SQLAlchemy database session.
        email: User email address.
        password: Plaintext user password.
        role: Assigned user authorization role.
        
    Returns:
        Created and committed User instance.
        
    Raises:
        ValueError: If email already exists or role is invalid.
    """
    clean_email = email.strip()
    clean_role = role.strip().upper()

    if clean_role not in UserRole.ALL_ROLES:
        raise ValueError(f"Invalid role '{role}'. Must be one of: {UserRole.ALL_ROLES}")

    existing_user = db.query(User).filter(User.email == clean_email).first()
    if existing_user:
        raise ValueError("An account with this email already exists.")

    hashed_pw = hash_password(password)
    user = User(
        email=clean_email,
        hashed_password=hashed_pw,
        role=clean_role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
