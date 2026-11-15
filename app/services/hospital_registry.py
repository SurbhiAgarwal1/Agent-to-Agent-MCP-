"""Bengaluru hospital directory in the main database, and registering hospitals that are not listed yet."""
import re

from sqlalchemy.orm import Session

from app.models.hospital import Hospital
from data_apis.bangalore_hospitals import BANGALORE_CENTRE, HOSPITALS, hospital_rows

_STOP = {"hospital", "hospitals", "the", "at", "in", "of", "and", "centre", "center", "medical", "institute", "general"}


def ensure_bangalore_hospitals(db: Session) -> int:
    """Add any directory hospital that is missing. Safe to run on every start. Returns how many were added."""
    have = {n.lower() for (n,) in db.query(Hospital.name).all()}
    added = 0
    for name, address, lat, lon in hospital_rows():
        if name.lower() not in have:
            db.add(Hospital(name=name, address=address, latitude=lat, longitude=lon))
            added += 1
    if added:
        db.commit()
    return added


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 1 and t not in _STOP]


def search_hospitals(db: Session, text: str) -> list[Hospital]:
    """Hospitals whose name, short names or area contain every meaningful word typed (word-order independent)."""
    want = tokens(text)
    if not want:
        return []
    short_names = {name: " ".join(al) for name, al, _a, _la, _lo in HOSPITALS}
    found = []
    for h in db.query(Hospital).order_by(Hospital.hospital_id.asc()).all():
        hay = set(tokens(f"{h.name} {h.address} {short_names.get(h.name, '')}"))
        if all(any(w == x or x.startswith(w) for x in hay) for w in want):
            found.append(h)
    return found


def register_hospital(db: Session, name: str) -> Hospital:
    """A hospital nobody has requested for yet: store it by the name staff typed. Its exact position is unknown, so it
    is placed at the centre of Bengaluru until someone corrects it."""
    clean = re.sub(r"\s+", " ", name).strip(" .,-")[:150]
    clean = " ".join(w if w.isupper() else w.capitalize() for w in clean.split(" "))
    hospital = Hospital(name=clean, address="Bengaluru (exact location not provided)", latitude=BANGALORE_CENTRE[0], longitude=BANGALORE_CENTRE[1])
    db.add(hospital)
    db.commit()
    db.refresh(hospital)
    return hospital
