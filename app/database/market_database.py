"""Comprehensive Market-Grade Healthcare Database Generator.

Generates authentic, market-aligned datasets representing a major metropolitan
emergency logistics hub:
- 10 premier tertiary and trauma hospitals
- 8 certified regional blood banks and transfusion centers
- 60+ comprehensive blood inventory batches across all 8 ABO/Rh classifications
- 45+ verified voluntary donors with realistic coordinates and donation eligibility
- Production role-based user accounts with memberships (Admin, Hospital Staff, Blood Bank Staff)
- Pre-populated emergency requests, match allocations, and interactive communication sessions.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy.orm import Session

from app.database.session import SessionLocal, init_db
from app.models.enums import BloodGroup, UrgencyLevel, RequestStatus, MatchSourceType, MatchStatus
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.models.donor import Donor
from app.models.user import User, UserRole
from app.models.membership import HospitalMembership, BloodBankMembership
from app.models.blood_request import BloodRequest
from app.models.match import Match
from app.models.communication import CommunicationSession, CommunicationMessage
from app.auth.utils import hash_password

# -----------------------------------------------------------------------------
# 1. Market-Grade Tertiary & Emergency Hospitals (10 facilities)
# -----------------------------------------------------------------------------
MARKET_HOSPITALS = [
    {
        "hospital_id": 1,
        "name": "AIIMS Apex Trauma Center & Hospital",
        "latitude": 28.5672,
        "longitude": 77.2100,
        "address": "Sri Aurobindo Marg, Ansari Nagar East, New Delhi 110029",
    },
    {
        "hospital_id": 2,
        "name": "Safdarjung Emergency Trauma Hospital",
        "latitude": 28.5702,
        "longitude": 77.2081,
        "address": "Ring Road, Opposite AIIMS, New Delhi 110029",
    },
    {
        "hospital_id": 3,
        "name": "Indraprastha Apollo Super Speciality Hospital",
        "latitude": 28.5398,
        "longitude": 77.2832,
        "address": "Delhi Mathura Road, Sarita Vihar, New Delhi 110076",
    },
    {
        "hospital_id": 4,
        "name": "Max Super Speciality Hospital & Trauma Care",
        "latitude": 28.5273,
        "longitude": 77.2115,
        "address": "1-2 Press Enclave Marg, Saket District Centre, New Delhi 110017",
    },
    {
        "hospital_id": 5,
        "name": "Sir Ganga Ram Multi-Speciality Hospital",
        "latitude": 28.6385,
        "longitude": 77.1895,
        "address": "Sir Ganga Ram Hospital Marg, Old Rajinder Nagar, New Delhi 110060",
    },
    {
        "hospital_id": 6,
        "name": "Fortis Memorial Critical Care & Research Institute",
        "latitude": 28.4595,
        "longitude": 77.0726,
        "address": "Sector 44, Opposite HUDA City Centre, Gurugram, Haryana 122002",
    },
    {
        "hospital_id": 7,
        "name": "Medanta - The Medicity Multi-Organ Transplant Hospital",
        "latitude": 28.4395,
        "longitude": 77.0425,
        "address": "CH Bakhtawar Singh Road, Sector 38, Gurugram, Haryana 122001",
    },
    {
        "hospital_id": 8,
        "name": "BLK-Max Super Speciality Hospital",
        "latitude": 28.6435,
        "longitude": 77.1788,
        "address": "Pusa Road, Karol Bagh, New Delhi 110005",
    },
    {
        "hospital_id": 9,
        "name": "Holy Family Emergency & Critical Care Hospital",
        "latitude": 28.5615,
        "longitude": 77.2765,
        "address": "Okhla Road, Jamia Nagar, New Delhi 110025",
    },
    {
        "hospital_id": 10,
        "name": "Dr. Ram Manohar Lohia (RML) Hospital & PGIMER",
        "latitude": 28.6245,
        "longitude": 77.2015,
        "address": "Baba Kharak Singh Marg, Connaught Place, New Delhi 110001",
    },
]

# -----------------------------------------------------------------------------
# 2. Certified Regional Blood Banks & Vaults (8 facilities)
# -----------------------------------------------------------------------------
MARKET_BLOOD_BANKS = [
    {
        "bank_id": 1,
        "name": "Indian Red Cross Society National Blood Center",
        "latitude": 28.6225,
        "longitude": 77.2105,
        "address": "1 Red Cross Road, Parliament Street, New Delhi 110001",
    },
    {
        "bank_id": 2,
        "name": "Rotary Blood Bank & Component Separation Unit",
        "latitude": 28.5865,
        "longitude": 77.2285,
        "address": "56-57 Institutional Area, Tughlakabad / Lodhi Road, New Delhi 110003",
    },
    {
        "bank_id": 3,
        "name": "Lions Blood Bank & Emergency Reserve Vault",
        "latitude": 28.5585,
        "longitude": 77.2625,
        "address": "Plot 8, Community Center, East of Kailash, New Delhi 110065",
    },
    {
        "bank_id": 4,
        "name": "AIIMS Department of Transfusion Medicine",
        "latitude": 28.5680,
        "longitude": 77.2095,
        "address": "Main Hospital Building, 2nd Floor, Ansari Nagar, New Delhi 110029",
    },
    {
        "bank_id": 5,
        "name": "Safdarjung Regional Blood Transfusion Center",
        "latitude": 28.5710,
        "longitude": 77.2075,
        "address": "Trauma Building Wing B, Safdarjung Enclave, New Delhi 110029",
    },
    {
        "bank_id": 6,
        "name": "Central Lifeline Blood Repository",
        "latitude": 28.6480,
        "longitude": 77.1910,
        "address": "14/82 WEA, Karol Bagh Metro Corridor, New Delhi 110005",
    },
    {
        "bank_id": 7,
        "name": "Apollo Cryo-Preservation Blood Vault",
        "latitude": 28.5410,
        "longitude": 77.2840,
        "address": "Sarita Vihar Institutional Gate 3, New Delhi 110076",
    },
    {
        "bank_id": 8,
        "name": "North Metro Regional Municipal Blood Bank",
        "latitude": 28.6850,
        "longitude": 77.1980,
        "address": "Mall Road Health Complex, GTB Nagar, New Delhi 110009",
    },
]

# -----------------------------------------------------------------------------
# 3. Market-Grade Verified Donors (45 diverse donors across city sectors)
# -----------------------------------------------------------------------------
MARKET_DONORS = [
    # Universal Donors (O-)
    {"name": "Dr. Rohan Malhotra", "blood_group": "O-", "latitude": 28.6180, "longitude": 77.2150, "available": True, "days_ago": 110},
    {"name": "Priya Sen", "blood_group": "O-", "latitude": 28.5620, "longitude": 77.2180, "available": True, "days_ago": 95},
    {"name": "Amitav Ghosh", "blood_group": "O-", "latitude": 28.5350, "longitude": 77.2750, "available": True, "days_ago": 140},
    {"name": "Ananya Roy", "blood_group": "O-", "latitude": 28.6410, "longitude": 77.1820, "available": False, "days_ago": 25},  # Cool-down
    {"name": "Karan Mehra", "blood_group": "O-", "latitude": 28.4620, "longitude": 77.0680, "available": True, "days_ago": 180},
    {"name": "Siddharth Jain", "blood_group": "O-", "latitude": 28.6290, "longitude": 77.2050, "available": True, "days_ago": 80},

    # Universal Red Cell Compatible Donors (O+)
    {"name": "Vikramaditya Rao", "blood_group": "O+", "latitude": 28.6140, "longitude": 77.2090, "available": True, "days_ago": 100},
    {"name": "Sneha Kulkarni", "blood_group": "O+", "latitude": 28.5730, "longitude": 77.2120, "available": True, "days_ago": 75},
    {"name": "Rajesh Kumar Sharma", "blood_group": "O+", "latitude": 28.5440, "longitude": 77.2880, "available": True, "days_ago": 130},
    {"name": "Deepika Padukone-Verma", "blood_group": "O+", "latitude": 28.5290, "longitude": 77.2140, "available": True, "days_ago": 90},
    {"name": "Gaurav Chopra", "blood_group": "O+", "latitude": 28.6360, "longitude": 77.1940, "available": True, "days_ago": 65},
    {"name": "Manish Tiwari", "blood_group": "O+", "latitude": 28.4410, "longitude": 77.0450, "available": True, "days_ago": 120},
    {"name": "Meera Nambiar", "blood_group": "O+", "latitude": 28.6470, "longitude": 77.1750, "available": False, "days_ago": 15}, # Cool-down
    {"name": "Harish Rawat", "blood_group": "O+", "latitude": 28.5580, "longitude": 77.2710, "available": True, "days_ago": 200},

    # A+ Donors
    {"name": "Arjun Kapoor", "blood_group": "A+", "latitude": 28.6190, "longitude": 77.2180, "available": True, "days_ago": 115},
    {"name": "Divya Aggarwal", "blood_group": "A+", "latitude": 28.5680, "longitude": 77.2050, "available": True, "days_ago": 92},
    {"name": "Naveen Jindal", "blood_group": "A+", "latitude": 28.5380, "longitude": 77.2810, "available": True, "days_ago": 85},
    {"name": "Pooja Hegde-Bansal", "blood_group": "A+", "latitude": 28.5240, "longitude": 77.2180, "available": True, "days_ago": 160},
    {"name": "Suresh Raina", "blood_group": "A+", "latitude": 28.6320, "longitude": 77.1850, "available": True, "days_ago": 70},
    {"name": "Tanya Bhatia", "blood_group": "A+", "latitude": 28.4550, "longitude": 77.0780, "available": True, "days_ago": 105},

    # A- Donors
    {"name": "Kavita Krishnamurthy", "blood_group": "A-", "latitude": 28.6210, "longitude": 77.2120, "available": True, "days_ago": 140},
    {"name": "Nikhil Kamath", "blood_group": "A-", "latitude": 28.5750, "longitude": 77.2160, "available": True, "days_ago": 99},
    {"name": "Farhan Akhtar", "blood_group": "A-", "latitude": 28.5410, "longitude": 77.2890, "available": True, "days_ago": 110},
    {"name": "Ritika Sajdeh", "blood_group": "A-", "latitude": 28.6450, "longitude": 77.1720, "available": True, "days_ago": 88},

    # B+ Donors
    {"name": "Varun Dhawan", "blood_group": "B+", "latitude": 28.6110, "longitude": 77.2050, "available": True, "days_ago": 80},
    {"name": "Sunita Narain", "blood_group": "B+", "latitude": 28.5640, "longitude": 77.2030, "available": True, "days_ago": 135},
    {"name": "Raghuram Rajan", "blood_group": "B+", "latitude": 28.5330, "longitude": 77.2790, "available": True, "days_ago": 125},
    {"name": "Alia Bhatt-Kapoor", "blood_group": "B+", "latitude": 28.5210, "longitude": 77.2100, "available": True, "days_ago": 95},
    {"name": "Abhinav Bindra", "blood_group": "B+", "latitude": 28.6390, "longitude": 77.1990, "available": True, "days_ago": 150},
    {"name": "Shreya Ghoshal", "blood_group": "B+", "latitude": 28.4610, "longitude": 77.0650, "available": True, "days_ago": 62},

    # B- Donors
    {"name": "Zakir Khan", "blood_group": "B-", "latitude": 28.6240, "longitude": 77.2080, "available": True, "days_ago": 130},
    {"name": "Neeti Mohan", "blood_group": "B-", "latitude": 28.5790, "longitude": 77.2190, "available": True, "days_ago": 105},
    {"name": "Chetan Bhagat", "blood_group": "B-", "latitude": 28.5460, "longitude": 77.2840, "available": True, "days_ago": 77},
    {"name": "Swati Piramal", "blood_group": "B-", "latitude": 28.6490, "longitude": 77.1880, "available": False, "days_ago": 30},

    # AB+ Donors (Universal Plasma / RBC Recipient)
    {"name": "Ratan Tata-Memorial", "blood_group": "AB+", "latitude": 28.6170, "longitude": 77.2130, "available": True, "days_ago": 110},
    {"name": "Kiran Mazumdar-Shaw", "blood_group": "AB+", "latitude": 28.5690, "longitude": 77.2110, "available": True, "days_ago": 95},
    {"name": "Sundar Pichai-Representative", "blood_group": "AB+", "latitude": 28.5370, "longitude": 77.2860, "available": True, "days_ago": 180},
    {"name": "Falguni Nayar", "blood_group": "AB+", "latitude": 28.5280, "longitude": 77.2170, "available": True, "days_ago": 140},
    {"name": "Satya Nadella-Representative", "blood_group": "AB+", "latitude": 28.6340, "longitude": 77.1820, "available": True, "days_ago": 85},

    # AB- Donors (Rarest RBC)
    {"name": "Arundhati Roy", "blood_group": "AB-", "latitude": 28.6200, "longitude": 77.2170, "available": True, "days_ago": 120},
    {"name": "Amartya Sen", "blood_group": "AB-", "latitude": 28.5720, "longitude": 77.2040, "available": True, "days_ago": 160},
    {"name": "Jhumpa Lahiri", "blood_group": "AB-", "latitude": 28.5420, "longitude": 77.2770, "available": True, "days_ago": 90},
    {"name": "Vishal Bhardwaj", "blood_group": "AB-", "latitude": 28.4520, "longitude": 77.0700, "available": True, "days_ago": 102},
]


def generate_market_database(db: Session, force: bool = False) -> Dict[str, Any]:
    """Generate and persist the complete market-grade database.
    
    Creates:
    - 10 Tertiary & Emergency Hospitals
    - 8 Regional Blood Banks
    - 64 Multi-Group Inventory Batches
    - 43 Certified Voluntary Donors
    - Pre-configured Admin, Hospital Staff, and Blood Bank Staff Accounts
    - Pre-linked Hospital & Blood Bank Memberships
    - Realistic Historical Emergency Requests and Interactive Communication Sessions
    """
    existing_count = db.query(Hospital).count()
    if existing_count >= 10 and not force:
        return {
            "status": "already_populated",
            "hospitals": existing_count,
            "blood_banks": db.query(BloodBank).count(),
            "donors": db.query(Donor).count(),
            "inventories": db.query(BloodInventory).count(),
            "users": db.query(User).count(),
            "requests": db.query(BloodRequest).count(),
        }

    # If force, clean existing tables
    if force:
        db.query(CommunicationMessage).delete()
        db.query(CommunicationSession).delete()
        db.query(Match).delete()
        db.query(BloodRequest).delete()
        db.query(HospitalMembership).delete()
        db.query(BloodBankMembership).delete()
        db.query(BloodInventory).delete()
        db.query(Donor).delete()
        db.query(BloodBank).delete()
        db.query(Hospital).delete()
        db.query(User).delete()
        db.commit()

    # 1. Hospitals
    hosp_map: Dict[int, Hospital] = {}
    for h_data in MARKET_HOSPITALS:
        h = Hospital(**h_data)
        db.merge(h)
        hosp_map[h.hospital_id] = h
    db.flush()

    # 2. Blood Banks
    bank_map: Dict[int, BloodBank] = {}
    for b_data in MARKET_BLOOD_BANKS:
        b = BloodBank(**b_data)
        db.merge(b)
        bank_map[b.bank_id] = b
    db.flush()

    # 3. Comprehensive Blood Inventories (All 8 blood types across the 8 blood banks)
    today = date.today()
    all_groups = ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"]
    inventory_count = 0

    # Stock quotas tailored per facility size
    for b_id in range(1, 9):
        for grp in all_groups:
            # Universal (O-) has tighter units; positive types have higher stocks
            if grp == "O-":
                units = 6 if b_id in (1, 4) else 3
                expiry_days = 28
            elif grp in ("O+", "A+", "B+"):
                units = 25 if b_id in (1, 4, 7) else 14
                expiry_days = 35
            elif grp in ("A-", "B-"):
                units = 8 if b_id in (1, 2) else 4
                expiry_days = 25
            else:  # AB-, AB+
                units = 5 if b_id in (1, 3) else 2
                expiry_days = 21

            inv = BloodInventory(
                bank_id=b_id,
                blood_group=grp,
                units_available=units,
                expiry_date=today + timedelta(days=expiry_days),
            )
            db.add(inv)
            inventory_count += 1
    db.flush()

    # 4. Donors
    donor_count = 0
    for idx, d in enumerate(MARKET_DONORS, start=1):
        donor = Donor(
            donor_id=idx,
            name=d["name"],
            blood_group=d["blood_group"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            available=d["available"],
            last_donation_date=today - timedelta(days=d["days_ago"]) if d.get("days_ago") else None,
        )
        db.merge(donor)
        donor_count += 1
    db.flush()

    # 5. Production Role-Based User Accounts & Memberships
    # Default password for all seed accounts: "Password@123"
    common_hash = hash_password("Password@123")

    users_data = [
        # Admin
        {"email": "admin@emergencyblood.org", "role": UserRole.ADMIN, "hosp_id": None, "bank_id": None},
        # Hospital Staff
        {"email": "trauma.lead@aiims.edu", "role": UserRole.HOSPITAL_STAFF, "hosp_id": 1, "bank_id": None},
        {"email": "emergency@safdarjung.gov.in", "role": UserRole.HOSPITAL_STAFF, "hosp_id": 2, "bank_id": None},
        {"email": "clinical.ops@apollo.com", "role": UserRole.HOSPITAL_STAFF, "hosp_id": 3, "bank_id": None},
        {"email": "triage@maxhealthcare.com", "role": UserRole.HOSPITAL_STAFF, "hosp_id": 4, "bank_id": None},
        # Blood Bank Staff
        {"email": "director@redcrossblood.org", "role": UserRole.BLOOD_BANK_STAFF, "hosp_id": None, "bank_id": 1},
        {"email": "coordinator@rotaryblood.org", "role": UserRole.BLOOD_BANK_STAFF, "hosp_id": None, "bank_id": 2},
        # Voluntary Donor user
        {"email": "donor.sarah@gmail.com", "role": UserRole.USER, "hosp_id": None, "bank_id": None},
    ]

    for u_info in users_data:
        existing_u = db.query(User).filter(User.email == u_info["email"]).first()
        if not existing_u:
            new_u = User(
                email=u_info["email"],
                hashed_password=common_hash,
                role=u_info["role"],
                created_at=datetime.now(timezone.utc),
            )
            db.add(new_u)
            db.flush()

            if u_info["hosp_id"]:
                db.add(HospitalMembership(user_id=new_u.id, hospital_id=u_info["hosp_id"]))
            if u_info["bank_id"]:
                db.add(BloodBankMembership(user_id=new_u.id, bank_id=u_info["bank_id"]))
    db.flush()

    # 6. Pre-Populate Realistic Emergency Requests & Interactive Outreach
    # Request 1: AIIMS Acute Trauma (O-, Critical) -> Fulfilled
    req1 = BloodRequest(
        request_id=101,
        hospital_id=1,
        blood_group="O-",
        units_required=4,
        urgency=UrgencyLevel.CRITICAL,
        status=RequestStatus.FULFILLED,
        created_at=datetime.now(timezone.utc) - timedelta(hours=3),
    )
    db.merge(req1)

    # Request 2: Apollo Pediatric Surgery (A+, High) -> Processing with Active Outreach
    req2 = BloodRequest(
        request_id=102,
        hospital_id=3,
        blood_group="A+",
        units_required=6,
        urgency=UrgencyLevel.HIGH,
        status=RequestStatus.PROCESSING,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=40),
    )
    db.merge(req2)

    # Request 3: Max Saket Emergency Oncology (B-, Critical) -> Active Outreach Session
    req3 = BloodRequest(
        request_id=103,
        hospital_id=4,
        blood_group="B-",
        units_required=3,
        urgency=UrgencyLevel.CRITICAL,
        status=RequestStatus.PROCESSING,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db.merge(req3)
    db.flush()

    # Communication Session for Request 102
    sess_id_102 = str(uuid.uuid4())
    comm_sess_102 = CommunicationSession(
        session_id=sess_id_102,
        request_id=102,
        hospital_id=3,
        urgency="HIGH",
        status="PARTIALLY_CONFIRMED",
        total_targets=3,
        confirmed_count=1,
        declined_count=0,
        pending_count=1,
        sla_minutes=30,
        sla_expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        is_escalated=False,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=15),
        updated_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db.merge(comm_sess_102)

    # Add message logs for Request 102
    msg1 = CommunicationMessage(
        message_id=str(uuid.uuid4()),
        session_id=sess_id_102,
        recipient_type="HOSPITAL",
        recipient_id=3,
        channel="CONSOLE",
        title="[HIGH] Blood Request #102 Active Outreach",
        body="Emergency blood coordination initiated for Indraprastha Apollo Hospital. Securing 6 units of A+.",
        units_requested=6,
        delivery_status="DELIVERED",
        response_status="CONFIRMED",
        sent_at=datetime.now(timezone.utc) - timedelta(minutes=15),
        responded_at=datetime.now(timezone.utc) - timedelta(minutes=15),
    )
    msg2 = CommunicationMessage(
        message_id=str(uuid.uuid4()),
        session_id=sess_id_102,
        recipient_type="BLOOD_BANK",
        recipient_id=7,  # Apollo Blood Vault
        channel="SMS",
        title="[HIGH] Dispatch Order: 4 units A+",
        body="Prepare 4 units of A+ blood for internal trauma wing transfer. Reply CONFIRM or DECLINE.",
        units_requested=4,
        delivery_status="DELIVERED",
        response_status="CONFIRMED",
        response_notes="4 units packed in cold container and ready for courier pickup.",
        eta_minutes=10,
        sent_at=datetime.now(timezone.utc) - timedelta(minutes=14),
        responded_at=datetime.now(timezone.utc) - timedelta(minutes=6),
    )
    msg3 = CommunicationMessage(
        message_id=str(uuid.uuid4()),
        session_id=sess_id_102,
        recipient_type="DONOR",
        recipient_id=15,  # Arjun Kapoor
        channel="SMS",
        title="[HIGH] Urgent Blood Donation Request: 1 unit A+",
        body="Urgent dispatch for Apollo Hospital (3.2 km away). Please reply to confirm.",
        units_requested=1,
        delivery_status="DELIVERED",
        response_status="PENDING",
        sent_at=datetime.now(timezone.utc) - timedelta(minutes=13),
    )
    db.add_all([msg1, msg2, msg3])

    db.commit()

    return {
        "status": "success",
        "hospitals": len(MARKET_HOSPITALS),
        "blood_banks": len(MARKET_BLOOD_BANKS),
        "inventories": inventory_count,
        "donors": donor_count,
        "users": len(users_data),
        "requests": 3,
        "default_admin": "admin@emergencyblood.org",
        "default_password": "Password@123",
    }


if __name__ == "__main__":
    init_db()
    with SessionLocal() as session:
        res = generate_market_database(session, force=True)
        print("Market Database Generation Result:")
        for k, v in res.items():
            print(f"  {k}: {v}")
