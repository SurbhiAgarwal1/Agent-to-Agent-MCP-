import pytest
from app.database.session import Base, SessionLocal, engine
from app.database.seed import seed_database
from app.models.pharmacy import Pharmacy, Medicine, MedicineInventory, MedicineOrder
from app.services.pharmacy_service import PharmacyFulfillmentService, haversine_km


@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_database(db)
    yield db
    db.close()


def test_haversine_calculation():
    # CP to South Ext is approximately 6-8 km in New Delhi
    dist = haversine_km(28.6315, 77.2167, 28.5729, 77.2223)
    assert 6.0 <= dist <= 8.5


def test_truemeds_substitute_matching(db_session):
    service = PharmacyFulfillmentService(db_session)
    dolo = db_session.query(Medicine).filter(Medicine.brand_name == "Dolo 650").first()
    assert dolo is not None

    substitutes = service.find_substitutes(dolo.medicine_id)
    assert len(substitutes) >= 1
    # Calpol 650 shares Paracetamol 650mg
    brand_names = [s.brand_name for s in substitutes]
    assert "Calpol 650" in brand_names


def test_nearest_pharmacy_and_order_reservation(db_session):
    service = PharmacyFulfillmentService(db_session)
    dolo = db_session.query(Medicine).filter(Medicine.brand_name == "Dolo 650").first()
    assert dolo is not None

    # Delivery location near Connaught Place
    deliv_lat = 28.6300
    deliv_lon = 28.6300

    order = service.reserve_and_create_order(
        user_id=None,
        hospital_id=None,
        delivery_address="Connaught Place, New Delhi",
        delivery_lat=28.6300,
        delivery_lon=77.2150,
        items=[{"medicine_id": dolo.medicine_id, "quantity": 2, "allow_substitute": True}],
        urgency="HIGH",
    )

    assert order.order_id is not None
    assert order.status == "MATCHED"
    assert order.total_amount > 0
    assert order.estimated_eta_minutes is not None
    assert len(order.items) == 1
    assert order.items[0].quantity == 2
