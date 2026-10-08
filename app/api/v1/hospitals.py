"""FastAPI router for hospital resources."""

from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.hospital import Hospital

router = APIRouter()


class HospitalSummary(BaseModel):
    """Schema for hospital summary in dropdowns and lists."""
    hospital_id: int
    name: str
    latitude: float
    longitude: float
    address: str

    model_config = ConfigDict(from_attributes=True)


@router.get(
    "",
    response_model=List[HospitalSummary],
    summary="List all registered hospitals",
    description="Returns a list of all registered hospitals with their coordinates and addresses.",
)
def list_hospitals(db: Session = Depends(get_db)):
    """Retrieve all hospitals from the database."""
    return db.query(Hospital).order_by(Hospital.hospital_id.asc()).all()
