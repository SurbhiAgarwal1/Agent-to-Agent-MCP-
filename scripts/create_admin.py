# Must be run from repo root as: python -m scripts.create_admin --email admin@example.com
"""CLI utility to create an initial administrator account."""

import argparse
import getpass
import sys

from app.database.session import init_db, SessionLocal
from app.models.user import UserRole
from app.services.user_service import create_user


def main():
    parser = argparse.ArgumentParser(description="Create an administrator user account.")
    parser.add_argument("--email", required=True, help="Administrator email address")
    args = parser.parse_args()

    email = args.email.strip()
    if not email:
        print("❌ Error: Email address cannot be empty.", file=sys.stderr)
        sys.exit(1)

    print(f"Creating administrator account for: {email}")
    password = getpass.getpass("Enter password: ")
    if not password:
        print("❌ Error: Password cannot be empty.", file=sys.stderr)
        sys.exit(1)

    password_confirm = getpass.getpass("Confirm password: ")
    if password != password_confirm:
        print("❌ Error: Passwords do not match.", file=sys.stderr)
        sys.exit(1)

    if len(password) < 6:
        print("❌ Error: Password must be at least 6 characters long.", file=sys.stderr)
        sys.exit(1)

    init_db()
    db = SessionLocal()
    try:
        user = create_user(db=db, email=email, password=password, role=UserRole.ADMIN)
        print(f"✅ Successfully created ADMIN account (User ID: {user.id}) for {user.email}")
    except ValueError as exc:
        print(f"❌ Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
