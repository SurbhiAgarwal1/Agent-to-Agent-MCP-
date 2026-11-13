"""Run the additive donor-notification schema migration on the configured database."""
import json
from donor_api.models import Base  # noqa: F401 - register ORM tables
from donor_api.database import engine
from donor_api.migrations import migrate_donor_notifications

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print(json.dumps(migrate_donor_notifications(engine), indent=2))
