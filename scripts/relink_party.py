"""Point a blood bank / donor login at an existing data-service record.

    python -m scripts.relink_party --email staff@example.com --bank-id 76
    python -m scripts.relink_party --email donor@example.com --donor-id 12
"""
import argparse

from app.database.session import SessionLocal
from app.models.party_link import PartyLink
from app.models.user import User


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bank-id", type=int)
    g.add_argument("--donor-id", type=int)
    a = ap.parse_args()
    kind, ext = ("blood_bank", a.bank_id) if a.bank_id else ("donor", a.donor_id)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == a.email.strip()).first()
        if user is None:
            raise SystemExit(f"No account with email {a.email}")
        taken = db.query(PartyLink).filter(PartyLink.kind == kind, PartyLink.external_id == ext, PartyLink.user_id != user.id).first()
        if taken:
            raise SystemExit(f"{kind} #{ext} is already linked to another account (user id {taken.user_id}).")
        link = db.query(PartyLink).filter(PartyLink.user_id == user.id).first()
        if link is None:
            db.add(PartyLink(user_id=user.id, kind=kind, external_id=ext))
        else:
            link.kind, link.external_id = kind, ext
        db.commit()
        print(f"{a.email} is now linked to {kind} #{ext}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
