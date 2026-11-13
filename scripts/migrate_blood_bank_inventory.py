"""Run the safe two-component migration on the configured blood-bank database."""
import json
from blood_bank_api.models import Base  # noqa: F401 - register ORM tables
from blood_bank_api.database import engine
from blood_bank_api.migrations import migrate_component_inventory, migrate_bank_notification_tokens

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print(json.dumps(migrate_component_inventory(engine), indent=2))
    print(json.dumps(migrate_bank_notification_tokens(engine), indent=2))
