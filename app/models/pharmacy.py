"""Models for local partner pharmacies, medicine catalog, and order fulfillment.

Follows multi-sided online medicine delivery architecture (Netmeds / PharmEasy / Sanvivo / Truemeds):
- Local partner pharmacies with geo-location for fast hyperlocal delivery.
- Medicine catalog with generic active salts for Truemeds-style substitution.
- Real-time inventory tracking with reserved stock holds to avoid stockouts.
- Order lifecycle tracking from prescription/intake to dispatch and delivery.
"""

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from app.database.session import Base


class Pharmacy(Base):
    """Local independent partner pharmacy (Sanvivo / hyperlocal delivery node)."""
    __tablename__ = "pharmacies"

    pharmacy_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(150), nullable=False, index=True)
    license_number = Column(String(50), unique=True, nullable=False)
    address = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    contact_phone = Column(String(20), nullable=False)
    contact_email = Column(String(100), nullable=True)
    delivery_radius_km = Column(Float, nullable=False, default=10.0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    inventory = relationship("MedicineInventory", back_populates="pharmacy", cascade="all, delete-orphan")
    orders = relationship("MedicineOrder", back_populates="pharmacy")

    def __repr__(self) -> str:
        return f"<Pharmacy(id={self.pharmacy_id}, name='{self.name}', radius={self.delivery_radius_km}km)>"


class Medicine(Base):
    """Pharmaceutical product with active composition for Truemeds substitute matching."""
    __tablename__ = "medicines"

    medicine_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    brand_name = Column(String(150), nullable=False, index=True)
    generic_name = Column(String(200), nullable=False, index=True)  # Active chemical salt / composition
    manufacturer = Column(String(100), nullable=False)
    dosage_form = Column(String(50), nullable=False)  # Tablet, Capsule, Syrup, Injection, etc.
    strength = Column(String(50), nullable=False)     # e.g. "650mg", "500mg", "10ml"
    rx_required = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=True)

    # Relationships
    inventory_items = relationship("MedicineInventory", back_populates="medicine", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Medicine(id={self.medicine_id}, brand='{self.brand_name}', salt='{self.generic_name}')>"


class MedicineInventory(Base):
    """Real-time inventory and pricing per partner pharmacy."""
    __tablename__ = "medicine_inventory"

    inventory_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.pharmacy_id", ondelete="CASCADE"), nullable=False, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.medicine_id", ondelete="CASCADE"), nullable=False, index=True)
    batch_number = Column(String(50), nullable=False)
    expiry_date = Column(DateTime, nullable=False)
    units_in_stock = Column(Integer, nullable=False, default=0)
    units_reserved = Column(Integer, nullable=False, default=0)  # Active reservation lease
    unit_price = Column(Float, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    pharmacy = relationship("Pharmacy", back_populates="inventory")
    medicine = relationship("Medicine", back_populates="inventory_items")

    @property
    def units_available(self) -> int:
        return max(0, self.units_in_stock - self.units_reserved)

    def __repr__(self) -> str:
        return f"<MedicineInventory(id={self.inventory_id}, pharmacy={self.pharmacy_id}, med={self.medicine_id}, avail={self.units_available})>"


class MedicineOrder(Base):
    """Prescription & Medicine order placed by patient or hospital."""
    __tablename__ = "medicine_orders"

    order_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.hospital_id", ondelete="SET NULL"), nullable=True, index=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.pharmacy_id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="PENDING")  # PENDING, MATCHED, DISPATCHED, DELIVERED, CANCELLED
    urgency = Column(String(20), nullable=False, default="MEDIUM")
    delivery_address = Column(String(255), nullable=False)
    delivery_latitude = Column(Float, nullable=True)
    delivery_longitude = Column(Float, nullable=True)
    estimated_eta_minutes = Column(Integer, nullable=True)
    total_amount = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    delivered_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    hospital = relationship("Hospital", foreign_keys=[hospital_id])
    pharmacy = relationship("Pharmacy", back_populates="orders")
    items = relationship("MedicineOrderItem", back_populates="order", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<MedicineOrder(id={self.order_id}, status='{self.status}', amount={self.total_amount})>"


class MedicineOrderItem(Base):
    """Line item in a medicine order."""
    __tablename__ = "medicine_order_items"

    item_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("medicine_orders.order_id", ondelete="CASCADE"), nullable=False, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.medicine_id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    is_substitute = Column(Boolean, nullable=False, default=False)
    original_medicine_name = Column(String(150), nullable=True)

    # Relationships
    order = relationship("MedicineOrder", back_populates="items")
    medicine = relationship("Medicine")
