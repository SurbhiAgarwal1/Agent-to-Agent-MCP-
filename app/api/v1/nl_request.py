"""Natural Language API Endpoint (Part 14)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.llm.nl_interface import NLInterfaceAgent

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
):
    """Parse natural language blood request, validate, coordinate, and summarize."""
    agent = NLInterfaceAgent(db=db)
    return agent.process_request(payload.text)
