"""Synthetic seed data for development and demonstration.

Includes:
- Synthetic Hospitals
- Synthetic Blood Banks & Blood Inventories
- Synthetic Donors
- Synthetic Partner Pharmacies (Sanvivo / Netmeds / Apollo model)
- Synthetic Medicines & Salt Compositions (Truemeds generic substitute model)
- Real-time stock inventories
"""

from datetime import date, datetime, timedelta, timezone
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.database.session import SessionLocal, init_db
from app.models.enums import BloodGroup
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor
from app.models.pharmacy import Pharmacy, Medicine, MedicineInventory


# -----------------------------------------------------------------------------
# 1. Synthetic Hospitals (3 facilities)
# -----------------------------------------------------------------------------
SYNTHETIC_HOSPITALS = [
    {
        "name": "Metro City General Hospital",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "address": "12 Medical Square, Central District, Metro City",
    },
    {
        "name": "St. Jude Emergency Care Center",
        "latitude": 28.6353,
        "longitude": 77.2250,
        "address": "88 Healthcare Boulevard, North Zone, Metro City",
    },
    {
        "name": "Sunrise Trauma & Surgical Hospital",
        "latitude": 28.5900,
        "longitude": 77.2400,
        "address": "45 Lifeline Avenue, South Extension, Metro City",
    },
]

# -----------------------------------------------------------------------------
# 2. Synthetic Blood Banks (3 facilities)
# -----------------------------------------------------------------------------
SYNTHETIC_BLOOD_BANKS = [
    {
        "name": "Red Cross Central Blood Bank",
        "latitude": 28.6180,
        "longitude": 77.2150,
        "address": "5 Humanitarian Way, Civic Center, Metro City",
    },
    {
        "name": "LifeStream Community Blood Center",
        "latitude": 28.6290,
        "longitude": 77.2100,
        "address": "23 Hope Street, West District, Metro City",
    },
    {
        "name": "CityCare Regional Transfusion Facility",
        "latitude": 28.6010,
        "longitude": 77.2300,
        "address": "77 Pulse Circle, East Sector, Metro City",
    },
]

# -----------------------------------------------------------------------------
# 3. Synthetic Donors
# -----------------------------------------------------------------------------
SYNTHETIC_DONORS = [
    {
        "name": "Alex Mercer",
        "blood_group": BloodGroup.O_NEG.value,
        "latitude": 28.6150,
        "longitude": 77.2110,
        "contact_number": "+91-98765-01001",
        "is_available": True,
        "last_donation_date": date.today() - timedelta(days=120),
    },
    {
        "name": "Priya Sharma",
        "blood_group": BloodGroup.A_POS.value,
        "latitude": 28.6300,
        "longitude": 77.2200,
        "contact_number": "+91-98765-01002",
        "is_available": True,
        "last_donation_date": date.today() - timedelta(days=95),
    },
]

# -----------------------------------------------------------------------------
# 4. Synthetic Local Partner Pharmacies (Sanvivo / Apollo 24x7 network)
# -----------------------------------------------------------------------------
SYNTHETIC_PHARMACIES = [
    {
        "name": "Apollo Pharmacy - Connaught Place",
        "license_number": "DL-DEL-100201",
        "address": "B-Block, Inner Circle, Connaught Place, New Delhi",
        "latitude": 28.6315,
        "longitude": 77.2167,
        "contact_phone": "+91-11-2341001",
        "contact_email": "apollo.cp@partner.example.com",
        "delivery_radius_km": 12.0,
    },
    {
        "name": "MedPlus Chemist - South Ext",
        "license_number": "DL-DEL-100202",
        "address": "G-14, South Extension Part 1, New Delhi",
        "latitude": 28.5729,
        "longitude": 77.2223,
        "contact_phone": "+91-11-2462002",
        "contact_email": "medplus.southext@partner.example.com",
        "delivery_radius_km": 10.0,
    },
    {
        "name": "Sanvivo Local Community Pharmacy",
        "license_number": "DL-DEL-100203",
        "address": "42 Ring Road, Lajpat Nagar, New Delhi",
        "latitude": 28.5700,
        "longitude": 77.2400,
        "contact_phone": "+91-11-2983003",
        "contact_email": "sanvivo.delhi@partner.example.com",
        "delivery_radius_km": 15.0,
    },
]

# -----------------------------------------------------------------------------
# 5. Synthetic Medicine Catalog & Truemeds Salt Mapping
# -----------------------------------------------------------------------------
SYNTHETIC_MEDICINES = [
    {
        "brand_name": "Dolo 650",
        "generic_name": "Paracetamol 650mg",
        "manufacturer": "Micro Labs Ltd",
        "dosage_form": "Tablet",
        "strength": "650mg",
        "rx_required": False,
        "description": "Antipyretic and analgesic for pain relief and fever.",
    },
    {
        "brand_name": "Calpol 650",
        "generic_name": "Paracetamol 650mg",
        "manufacturer": "GlaxoSmithKline Pharmaceuticals",
        "dosage_form": "Tablet",
        "strength": "650mg",
        "rx_required": False,
        "description": "Generic equivalent to Dolo 650 sharing the same active salt.",
    },
    {
        "brand_name": "Augmentin 625 Duo",
        "generic_name": "Amoxicillin and Clavulanic Acid 625mg",
        "manufacturer": "GSK Ltd",
        "dosage_form": "Tablet",
        "strength": "625mg",
        "rx_required": True,
        "description": "Antibiotic used to treat bacterial infections.",
    },
    {
        "brand_name": "Moxikind-CV 625",
        "generic_name": "Amoxicillin and Clavulanic Acid 625mg",
        "manufacturer": "Mankind Pharma",
        "dosage_form": "Tablet",
        "strength": "625mg",
        "rx_required": True,
        "description": "Cost-effective Truemeds substitute for Augmentin 625.",
    },
    {
        "brand_name": "Azithral 500",
        "generic_name": "Azithromycin 500mg",
        "manufacturer": "Alembic Pharmaceuticals",
        "dosage_form": "Tablet",
        "strength": "500mg",
        "rx_required": True,
        "description": "Macrolide antibiotic for respiratory and skin infections.",
    },
    {
        "brand_name": "Pan 40",
        "generic_name": "Pantoprazole 40mg",
        "manufacturer": "Alkem Laboratories",
        "dosage_form": "Tablet",
        "strength": "40mg",
        "rx_required": False,
        "description": "Proton pump inhibitor that reduces stomach acid.",
    },
    {
        "brand_name": "Pantocid 40",
        "generic_name": "Pantoprazole 40mg",
        "manufacturer": "Sun Pharma",
        "dosage_form": "Tablet",
        "strength": "40mg",
        "rx_required": False,
        "description": "Equivalent generic formulation for acid reflux.",
    },
]


def seed_database(db: Session) -> Dict[str, Any]:
    """Populate database with synthetic development records."""
    summary: Dict[str, int] = {}

    # Seed hospitals
    if db.query(Hospital).count() == 0:
        hospitals = [Hospital(**h) for h in SYNTHETIC_HOSPITALS]
        db.add_all(hospitals)
        db.commit()
        summary["hospitals_created"] = len(hospitals)

    # Seed blood banks
    if db.query(BloodBank).count() == 0:
        blood_banks = [BloodBank(**b) for b in SYNTHETIC_BLOOD_BANKS]
        db.add_all(blood_banks)
        db.commit()
        summary["blood_banks_created"] = len(blood_banks)

    # Seed donors
    if db.query(Donor).count() == 0:
        donors = [Donor(**d) for d in SYNTHETIC_DONORS]
        db.add_all(donors)
        db.commit()
        summary["donors_created"] = len(donors)

    # Seed partner pharmacies
    if db.query(Pharmacy).count() == 0:
        pharmacies = [Pharmacy(**p) for p in SYNTHETIC_PHARMACIES]
        db.add_all(pharmacies)
        db.commit()
        summary["pharmacies_created"] = len(pharmacies)

    # Seed medicines catalog
    if db.query(Medicine).count() == 0:
        meds = [Medicine(**m) for m in SYNTHETIC_MEDICINES]
        db.add_all(meds)
        db.commit()
        summary["medicines_created"] = len(meds)

    # Seed medicine inventory across partner pharmacies
    if db.query(MedicineInventory).count() == 0:
        all_pharmacies = db.query(Pharmacy).all()
        all_meds = db.query(Medicine).all()
        now = datetime.now(timezone.utc)
        inv_items = []

        prices = {
            "Dolo 650": 30.0,
            "Calpol 650": 24.5,
            "Augmentin 625 Duo": 205.0,
            "Moxikind-CV 625": 140.0,
            "Azithral 500": 115.0,
            "Pan 40": 95.0,
            "Pantocid 40": 82.0,
        }

        for p_idx, pharm in enumerate(all_pharmacies):
            for m_idx, med in enumerate(all_meds):
                base_price = prices.get(med.brand_name, 50.0)
                inv = MedicineInventory(
                    pharmacy_id=pharm.pharmacy_id,
                    medicine_id=med.medicine_id,
                    batch_number=f"BCH-2026-{p_idx+1}{m_idx+1:02d}",
                    expiry_date=now + timedelta(days=365 + (m_idx * 30)),
                    units_in_stock=100 + (p_idx * 25) + (m_idx * 10),
                    units_reserved=0,
                    unit_price=base_price,
                )
                inv_items.append(inv)

        db.add_all(inv_items)
        db.commit()
        summary["inventory_items_created"] = len(inv_items)

    return summary


if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        results = seed_database(db)
        print("Database seeded successfully:", results)
    finally:
        db.close()
