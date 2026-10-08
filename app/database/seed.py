"""Synthetic seed data for development and demonstration.

IMPORTANT NOTICE:
All records generated in this module are strictly SYNTHETIC / FICTIONAL DEMO DATA
created for educational and testing purposes. No real hospital, blood bank, or
donor personally identifiable information (PII) is included.
"""

from datetime import date, timedelta
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.database.session import SessionLocal, init_db
from app.models.enums import BloodGroup
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor


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
        "address": "104 Ring Road Junction, South Suburb, Metro City",
    },
]

# -----------------------------------------------------------------------------
# 2. Synthetic Blood Banks (4 facilities)
# -----------------------------------------------------------------------------
SYNTHETIC_BLOOD_BANKS = [
    {
        "name": "Central Red Cross Blood Bank",
        "latitude": 28.6200,
        "longitude": 77.2150,
        "address": "44 Compassion Lane, Central District, Metro City",
    },
    {
        "name": "Lifeline Blood Repository",
        "latitude": 28.6400,
        "longitude": 77.2100,
        "address": "19 Hope Avenue, North Zone, Metro City",
    },
    {
        "name": "City Hope Community Blood Center",
        "latitude": 28.5850,
        "longitude": 77.2300,
        "address": "77 Civic Center Road, South Suburb, Metro City",
    },
    {
        "name": "Apex Emergency Blood Vault",
        "latitude": 28.6100,
        "longitude": 77.2600,
        "address": "250 Expressway Sector 4, East Zone, Metro City",
    },
]

# -----------------------------------------------------------------------------
# 3. Synthetic Donors (15 donors with varied blood groups and locations)
# -----------------------------------------------------------------------------
SYNTHETIC_DONORS = [
    {"name": "Synthetic Donor 01 (Alex M.)", "blood_group": BloodGroup.O_NEG.value, "latitude": 28.6150, "longitude": 77.2110, "available": True, "last_donation_date": date.today() - timedelta(days=120)},
    {"name": "Synthetic Donor 02 (Jordan L.)", "blood_group": BloodGroup.O_POS.value, "latitude": 28.6180, "longitude": 77.2190, "available": True, "last_donation_date": date.today() - timedelta(days=95)},
    {"name": "Synthetic Donor 03 (Taylor S.)", "blood_group": BloodGroup.A_POS.value, "latitude": 28.6220, "longitude": 77.2140, "available": True, "last_donation_date": date.today() - timedelta(days=110)},
    {"name": "Synthetic Donor 04 (Casey B.)", "blood_group": BloodGroup.A_NEG.value, "latitude": 28.6290, "longitude": 77.2280, "available": True, "last_donation_date": None},
    {"name": "Synthetic Donor 05 (Morgan K.)", "blood_group": BloodGroup.B_POS.value, "latitude": 28.6340, "longitude": 77.2220, "available": True, "last_donation_date": date.today() - timedelta(days=140)},
    {"name": "Synthetic Donor 06 (Riley P.)", "blood_group": BloodGroup.B_NEG.value, "latitude": 28.6410, "longitude": 77.2180, "available": False, "last_donation_date": date.today() - timedelta(days=20)},
    {"name": "Synthetic Donor 07 (Avery D.)", "blood_group": BloodGroup.AB_POS.value, "latitude": 28.5880, "longitude": 77.2350, "available": True, "last_donation_date": date.today() - timedelta(days=180)},
    {"name": "Synthetic Donor 08 (Quinn R.)", "blood_group": BloodGroup.AB_NEG.value, "latitude": 28.5920, "longitude": 77.2420, "available": True, "last_donation_date": None},
    {"name": "Synthetic Donor 09 (Sam T.)", "blood_group": BloodGroup.O_POS.value, "latitude": 28.6080, "longitude": 77.2550, "available": True, "last_donation_date": date.today() - timedelta(days=105)},
    {"name": "Synthetic Donor 10 (Jamie N.)", "blood_group": BloodGroup.O_NEG.value, "latitude": 28.6140, "longitude": 77.2620, "available": True, "last_donation_date": date.today() - timedelta(days=210)},
    {"name": "Synthetic Donor 11 (Dakota H.)", "blood_group": BloodGroup.A_POS.value, "latitude": 28.6110, "longitude": 77.2020, "available": False, "last_donation_date": date.today() - timedelta(days=15)},
    {"name": "Synthetic Donor 12 (Reese V.)", "blood_group": BloodGroup.B_POS.value, "latitude": 28.6260, "longitude": 77.2310, "available": True, "last_donation_date": date.today() - timedelta(days=92)},
    {"name": "Synthetic Donor 13 (Parker C.)", "blood_group": BloodGroup.A_NEG.value, "latitude": 28.5980, "longitude": 77.2280, "available": True, "last_donation_date": date.today() - timedelta(days=150)},
    {"name": "Synthetic Donor 14 (Kendall W.)", "blood_group": BloodGroup.O_POS.value, "latitude": 28.6380, "longitude": 77.2080, "available": True, "last_donation_date": None},
    {"name": "Synthetic Donor 15 (Skyler F.)", "blood_group": BloodGroup.B_NEG.value, "latitude": 28.6020, "longitude": 77.2480, "available": True, "last_donation_date": date.today() - timedelta(days=130)},
]

# -----------------------------------------------------------------------------
# 4. Initial Stock Matrix (group and units per blood bank index)
# -----------------------------------------------------------------------------
INITIAL_INVENTORY_TEMPLATES = [
    # Bank 0: Central Red Cross (well stocked)
    [
        (BloodGroup.O_POS.value, 12, 35),
        (BloodGroup.O_NEG.value, 4, 28),
        (BloodGroup.A_POS.value, 10, 40),
        (BloodGroup.A_NEG.value, 3, 25),
        (BloodGroup.B_POS.value, 8, 30),
        (BloodGroup.B_NEG.value, 2, 21),
        (BloodGroup.AB_POS.value, 5, 32),
        (BloodGroup.AB_NEG.value, 1, 18),
    ],
    # Bank 1: Lifeline Repository (moderate stock)
    [
        (BloodGroup.O_POS.value, 6, 20),
        (BloodGroup.O_NEG.value, 1, 15),
        (BloodGroup.A_POS.value, 8, 30),
        (BloodGroup.B_POS.value, 5, 25),
        (BloodGroup.AB_POS.value, 2, 22),
    ],
    # Bank 2: City Hope Center (south suburb stock)
    [
        (BloodGroup.O_POS.value, 9, 29),
        (BloodGroup.O_NEG.value, 2, 24),
        (BloodGroup.A_POS.value, 6, 31),
        (BloodGroup.A_NEG.value, 2, 19),
        (BloodGroup.B_POS.value, 7, 27),
        (BloodGroup.B_NEG.value, 1, 14),
    ],
    # Bank 3: Apex Emergency Vault (emergency buffer)
    [
        (BloodGroup.O_POS.value, 15, 42),
        (BloodGroup.O_NEG.value, 5, 35),
        (BloodGroup.A_POS.value, 10, 38),
        (BloodGroup.B_POS.value, 10, 36),
        (BloodGroup.AB_POS.value, 4, 28),
        (BloodGroup.AB_NEG.value, 2, 20),
    ],
]


def seed_database(db: Session, force: bool = False) -> Dict[str, Any]:
    """Populate the database with synthetic starter data if empty.
    
    Args:
        db: SQLAlchemy session
        force: If True, skips the empty-table guard and adds synthetic records.
        
    Returns:
        Summary dict of created record counts.
    """
    existing_hospitals = db.query(Hospital).count()
    if existing_hospitals > 0 and not force:
        return {
            "status": "already_seeded",
            "hospitals": existing_hospitals,
            "blood_banks": db.query(BloodBank).count(),
            "donors": db.query(Donor).count(),
            "inventories": db.query(BloodInventory).count(),
        }

    # 1. Insert Hospitals
    created_hospitals = []
    for h_data in SYNTHETIC_HOSPITALS:
        h = Hospital(**h_data)
        db.add(h)
        created_hospitals.append(h)
    db.flush()

    # 2. Insert Blood Banks
    created_banks = []
    for b_data in SYNTHETIC_BLOOD_BANKS:
        b = BloodBank(**b_data)
        db.add(b)
        created_banks.append(b)
    db.flush()

    # 3. Insert Inventory for each Blood Bank
    created_inventory = []
    today = date.today()
    for idx, bank in enumerate(created_banks):
        stock_list = INITIAL_INVENTORY_TEMPLATES[idx]
        for blood_grp, units, days_until_expiry in stock_list:
            inv = BloodInventory(
                bank_id=bank.bank_id,
                blood_group=blood_grp,
                units_available=units,
                expiry_date=today + timedelta(days=days_until_expiry),
            )
            db.add(inv)
            created_inventory.append(inv)
    db.flush()

    # 4. Insert Synthetic Donors
    created_donors = []
    for d_data in SYNTHETIC_DONORS:
        d = Donor(**d_data)
        db.add(d)
        created_donors.append(d)
    db.flush()

    db.commit()

    return {
        "status": "success",
        "hospitals": len(created_hospitals),
        "blood_banks": len(created_banks),
        "donors": len(created_donors),
        "inventories": len(created_inventory),
    }


if __name__ == "__main__":
    init_db()
    with SessionLocal() as session:
        result = seed_database(session)
        print("Database Seed Completed:")
        print(result)
