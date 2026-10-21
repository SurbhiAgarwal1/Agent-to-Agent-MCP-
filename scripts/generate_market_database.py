"""CLI Command to generate a realistic, market-grade healthcare database."""

import argparse
import sys

from app.database.session import SessionLocal, init_db
from app.database.market_database import generate_market_database


def main():
    parser = argparse.ArgumentParser(description="Generate comprehensive market-grade healthcare database.")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing database records.")
    args = parser.parse_args()

    print("=" * 70)
    print("  BLOOD DONATION MATCHING SYSTEM - MARKET DATABASE GENERATOR")
    print("  Generating real-world tertiary hospitals, certified blood banks,")
    print("  multi-group blood inventories, active donors, and staff accounts...")
    print("=" * 70)

    init_db()
    with SessionLocal() as session:
        result = generate_market_database(session, force=args.force)
        print("\n[+] Generation Summary:")
        for key, val in result.items():
            print(f"  - {key.replace('_', ' ').capitalize()}: {val}")

        print("\n[+] Quick Access Credentials (Password for all accounts: 'Password@123'):")
        print("  - System Administrator : admin@emergencyblood.org")
        print("  - AIIMS Trauma Lead    : trauma.lead@aiims.edu")
        print("  - Apollo Clinical Ops  : clinical.ops@apollo.com")
        print("  - Red Cross Director   : director@redcrossblood.org")
        print("=" * 70)


if __name__ == "__main__":
    main()
