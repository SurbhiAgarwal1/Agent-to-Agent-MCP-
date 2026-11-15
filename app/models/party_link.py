"""Ties a login account to its record in a data service (a donor or a blood bank listing)."""
from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from app.database.session import Base


class PartyLink(Base):
    __tablename__ = "party_links"
    __table_args__ = (UniqueConstraint("kind", "external_id", name="uq_party_link_kind_external"),)

    link_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    kind = Column(String(16), nullable=False)  # "donor" | "blood_bank"
    external_id = Column(Integer, nullable=False)
