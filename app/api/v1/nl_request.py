"""Natural Language API Endpoint (Part 14)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.agents.nl_interface import NLInterfaceAgent
from app.models.user import User, UserRole
from app.auth.dependencies import require_role
from app.auth.authorization import active_hospital_ids

router = APIRouter()


class NLRequestInput(BaseModel):
    text: str = Field(
        ...,
        description="Free-form emergency blood request description",
        json_schema_extra={"example": "We urgently need 2 units of A+ at General Hospital"},
    )


@router.post("/nl-request", tags=["Natural Language Interface"])
def process_natural_language_request(
    payload: NLRequestInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.HOSPITAL_STAFF, UserRole.ADMIN])),
):
    """Parse natural language blood request, validate, coordinate, and summarize."""
    agent = NLInterfaceAgent(db=db, network=True)
    allowed = None if current_user.role == UserRole.ADMIN else active_hospital_ids(db, current_user.id)
    result = agent.process_request(
    payload.text,
    current_user_id=current_user.id,
    allowed_hospital_ids=allowed,
)
    structured_result = result.get("structured_result") or {}

    if structured_result.get("failed_at") == "AUTHORIZATION":
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active membership in the requested hospital is required.")
    if result.get("status") == "FAILED":
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Natural-language request workflow could not be completed.")
    return result
