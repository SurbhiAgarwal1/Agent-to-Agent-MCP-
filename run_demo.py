"""End-to-End Local Demonstration Script for Blood Donation Matching System.

Demonstrates all components built in Parts 1-6:
1. Database & Seed Data
2. Requirement Agent (Validation & Normalization)
3. Matching Agent & Compatibility Service (Medically standard blood matching)
4. Location Agent & Haversine Distance (Spatial proximity & approximate ETA)
"""

from app.database.session import SessionLocal, init_db
from app.database.seed import seed_database
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.donor import Donor
from app.agents.requirement_agent import RequirementAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.location_agent import LocationAgent


def main():
    print("=" * 70)
    print("  BLOOD DONATION MATCHING & EMERGENCY COORDINATION SYSTEM")
    print("  Local Interactive Pipeline Demonstration (Parts 1 to 6)")
    print("=" * 70)

    # 1. Initialize Database and Ensure Seed Data Exists
    init_db()
    db = SessionLocal()
    seed_database(db)

    # 2. Select Requesting Hospital
    hospital = db.query(Hospital).first()
    if not hospital:
        print("❌ Error: No hospitals found in database.")
        return

    print(f"\n[1] Hospital Requesting Blood:")
    print(f"    - Hospital Name: {hospital.name} (ID: {hospital.hospital_id})")
    print(f"    - Location: Lat {hospital.latitude}, Lon {hospital.longitude}")
    print(f"    - Address: {hospital.address}")

    # Simulated incoming raw emergency request (with mixed casing)
    raw_request = {
        "request_id": 101,
        "hospital_id": hospital.hospital_id,
        "blood_group": "o+",
        "units_required": 4,
        "urgency": "critical",
    }
    print(f"\n[2] Raw Emergency Request Received:")
    print(f"    {raw_request}")

    # 3. Requirement Agent: Validation & Normalization
    print("\n" + "-" * 70)
    print("--> Step 1: Requirement Agent Validating & Normalizing Request...")
    req_agent = RequirementAgent(db=db)
    req_output = req_agent.process(raw_request)
    print(f"    - Validated Status: {req_output.get('valid')}")
    print(f"    - Normalized Group: {req_output.get('blood_group')}")
    print(f"    - Normalized Urgency: {req_output.get('urgency')}")
    print(f"    - Units Required: {req_output.get('units_required')}")

    if not req_output.get("valid"):
        print(f"[-] Validation failed: {req_output.get('errors')}")
        return

    # 4. Matching Agent: Find Compatible Blood Banks & Eligible Donors
    print("\n" + "-" * 70)
    print("--> Step 2: Matching Agent Discovering Compatible Sources...")
    match_agent = MatchingAgent(db=db)
    match_output = match_agent.find_matches(req_output)
    matches = match_output["matches"]
    print(f"    - Found {len(matches)} compatible matches in total.")

    # 5. Location Agent: Calculate Haversine Distances & Approximate ETAs
    print("\n" + "-" * 70)
    print("--> Step 3: Location Agent Calculating Distances & Approximate ETAs...")
    loc_agent = LocationAgent()

    results_table = []
    for m in matches:
        source_type = m["source_type"]
        source_id = m["source_id"]
        source_bg = m["blood_group"]
        units = m["units_available"]

        if source_type == "BLOOD_BANK":
            bank = db.query(BloodBank).filter(BloodBank.bank_id == source_id).first()
            name = bank.name if bank else f"Bank #{source_id}"
            distance_info = loc_agent.calculate_distance(
                origin_lat=hospital.latitude,
                origin_lon=hospital.longitude,
                dest_lat=bank.latitude,
                dest_lon=bank.longitude,
                include_eta=True,
            )
        else:
            donor = db.query(Donor).filter(Donor.donor_id == source_id).first()
            name = donor.name if donor else f"Donor #{source_id}"
            distance_info = loc_agent.calculate_distance(
                origin_lat=hospital.latitude,
                origin_lon=hospital.longitude,
                dest_lat=donor.latitude,
                dest_lon=donor.longitude,
                include_eta=True,
            )

        results_table.append({
            "type": source_type,
            "name": name,
            "group": source_bg,
            "units": units,
            "distance_km": distance_info["distance_km"],
            "eta": distance_info["estimated_time"],
        })

    # Display Candidates Table
    print("\n" + "=" * 85)
    print(f"{'Source Type':<12} | {'Name / Entity':<32} | {'Group':<5} | {'Stock':<5} | {'Distance':<10} | {'Approx ETA'}")
    print("=" * 85)
    for row in results_table:
        print(f"{row['type']:<12} | {row['name']:<32} | {row['group']:<5} | {row['units']:<5} | {row['distance_km']} km{'':<3} | {row['eta']}")
    print("=" * 85)
    print("\n[OK] Local pipeline demonstration completed successfully.\n")

    db.close()


if __name__ == "__main__":
    main()
