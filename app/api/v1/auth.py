"""Authentication and Audit Log API Endpoints (Part 15)."""

from typing import List, Optional
import secrets
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.config import get_settings
from app.models import User, UserRole, AuditLog, Hospital, BloodBank, HospitalMembership, BloodBankMembership
from app.schemas.auth import UserRegister, UserCreate, UserLogin, Token, UserResponse, MembershipGrant
from app.auth.utils import verify_password, create_access_token
from app.auth.dependencies import get_current_user, require_role
from app.services.user_service import create_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    """Register a new user account with role (public self-service registration)."""
    requested_role = (payload.role or UserRole.HOSPITAL_STAFF).strip().upper()

    if requested_role == UserRole.ADMIN:
        configured_key = get_settings().admin_signup_key.strip()
        provided_key = (payload.admin_signup_key or "").strip()
        if not configured_key or not provided_key or not secrets.compare_digest(provided_key, configured_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin registration requires the configured admin setup key.",
            )
    elif requested_role not in (UserRole.HOSPITAL_STAFF, UserRole.USER, UserRole.BLOOD_BANK_STAFF):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration can create HOSPITAL_STAFF, USER (donor), BLOOD_BANK_STAFF or ADMIN accounts.",
        )

    # Validate the role's profile and make sure the email is free BEFORE creating anything in the data services.
    if db.query(User).filter(User.email == payload.email.strip()).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="An account with this email already exists.")
    from app.models.party_link import PartyLink
    from app.services import party_service
    link = None
    if requested_role == UserRole.USER:
        group = (payload.blood_group or "").strip().upper()
        if group not in party_service.GROUPS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Donors must choose a blood group (A+, A-, B+, B-, AB+, AB-, O+, O-).")
        if payload.latitude is None or payload.longitude is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Donors must share their location (latitude and longitude).")
        donor_id = party_service.create_donor(
            name=(payload.name or payload.email.split("@")[0])[:120], age=payload.age or 25, blood_group=group,
            city=payload.city or "Unknown", district=payload.district or payload.city or "Unknown",
            state=payload.state or "Unknown", pin_code=payload.pin_code or "000000",
            latitude=payload.latitude, longitude=payload.longitude)
        link = ("donor", donor_id)
    elif requested_role == UserRole.BLOOD_BANK_STAFF:
        if not (payload.organization_name or "").strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter the name of your blood bank.")
        if payload.latitude is None or payload.longitude is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Share the blood bank's location (latitude and longitude).")
        stock = {k.upper(): int(v) for k, v in (payload.initial_stock or {}).items() if int(v) > 0}
        bad = [k for k in stock if k not in party_service.GROUPS]
        if bad:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown blood group in stock: {bad[0]}")
        bank_id = party_service.create_bank(
            name=payload.organization_name.strip(), address=(payload.address or payload.city or "Not provided").strip(),
            city=payload.city or "Unknown", district=payload.district or payload.city or "Unknown",
            state=payload.state or "Unknown", pin_code=payload.pin_code or "000000", latitude=payload.latitude,
            longitude=payload.longitude, contact_number=payload.contact_number,
            contact_email=payload.email.strip(), initial_stock=stock)
        link = ("blood_bank", bank_id)

    try:
        user = create_user(
            db=db,
            email=payload.email,
            password=payload.password,
            role=requested_role,
        )
        if link:
            db.add(PartyLink(user_id=user.id, kind=link[0], external_id=link[1]))
            db.commit()
        elif requested_role == UserRole.HOSPITAL_STAFF and (payload.organization_name or "").strip():
            hospital = Hospital(name=payload.organization_name.strip(), address=(payload.address or "Not provided").strip(),
                                latitude=payload.latitude if payload.latitude is not None else 0.0,
                                longitude=payload.longitude if payload.longitude is not None else 0.0)
            db.add(hospital)
            db.flush()
            db.add(HospitalMembership(user_id=user.id, hospital_id=hospital.hospital_id, membership_type="STAFF", is_active=True))
            db.commit()
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
    active_hospitals = [
        m.hospital_id for m in getattr(current_user, "hospital_memberships", []) if m.is_active
    ]
    active_banks = [
        m.bank_id for m in getattr(current_user, "blood_bank_memberships", []) if m.is_active
    ]
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        hospital_ids=active_hospitals,
        bank_ids=active_banks,
    )


@router.get("/audit-logs")
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
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


def _grant_membership(db, *, actor_id: int, user_id: int, org_id: int, model, org_field: str, membership_type: str):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    organization_model = Hospital if model is HospitalMembership else BloodBank
    if db.query(organization_model).filter(getattr(organization_model, org_field) == org_id).first() is None:
        raise HTTPException(status_code=404, detail="Organization not found.")
    required_role = UserRole.HOSPITAL_STAFF if model is HospitalMembership else UserRole.BLOOD_BANK_STAFF
    if user.role != required_role:
        raise HTTPException(status_code=403, detail="Membership type does not match the user's role.")

    membership = db.query(model).filter_by(user_id=user_id, **{org_field: org_id}).first()
    if membership is None:
        membership = model(user_id=user_id, **{org_field: org_id}, membership_type=membership_type, is_active=True)
        db.add(membership)
    else:
        membership.membership_type = membership_type
        membership.is_active = True
    db.commit()
    db.refresh(membership)
    from app.services.audit import record_audit_log
    record_audit_log(db, "GRANT_MEMBERSHIP", "organization_membership", membership.membership_id,
                     user_id=actor_id, details={"member_user_id": user_id, "organization_id": org_id})
    return {"membership_id": membership.membership_id, "user_id": user_id,
            "organization_id": org_id, "membership_type": membership.membership_type, "is_active": True}


@router.post("/users/{user_id}/hospital-memberships")
def grant_hospital_membership(
    payload: MembershipGrant,
    user_id: int = Path(gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    return _grant_membership(db, actor_id=current_user.id, user_id=user_id, org_id=payload.organization_id,
                             model=HospitalMembership, org_field="hospital_id", membership_type=payload.membership_type)


@router.post("/users/{user_id}/blood-bank-memberships")
def grant_blood_bank_membership(
    payload: MembershipGrant,
    user_id: int = Path(gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    return _grant_membership(db, actor_id=current_user.id, user_id=user_id, org_id=payload.organization_id,
                             model=BloodBankMembership, org_field="bank_id", membership_type=payload.membership_type)


def _revoke_membership(db, membership_id: int, model, actor_id: int):
    membership = db.query(model).filter_by(membership_id=membership_id).first()
    if membership is None:
        raise HTTPException(status_code=404, detail="Membership not found.")
    membership.is_active = False
    db.commit()
    from app.services.audit import record_audit_log
    record_audit_log(db, "REVOKE_MEMBERSHIP", "organization_membership", membership_id,
                     user_id=actor_id, details={"member_user_id": membership.user_id})
    return {"membership_id": membership_id, "is_active": False}


@router.delete("/hospital-memberships/{membership_id}")
def revoke_hospital_membership(membership_id: int = Path(gt=0), db: Session = Depends(get_db),
                               current_user: User = Depends(require_role([UserRole.ADMIN]))):
    return _revoke_membership(db, membership_id, HospitalMembership, current_user.id)


@router.delete("/blood-bank-memberships/{membership_id}")
def revoke_blood_bank_membership(membership_id: int = Path(gt=0), db: Session = Depends(get_db),
                                 current_user: User = Depends(require_role([UserRole.ADMIN]))):
    return _revoke_membership(db, membership_id, BloodBankMembership, current_user.id)
