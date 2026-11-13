"""Small, idempotent schema/data migrations for the independent bank database."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import inspect, text


SUPPORTED = ("whole_blood", "packed_red_blood_cells")
GROUPS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")


def migrate_component_inventory(engine):
    """Normalize legacy four-component stock to two safe components and two rows per pair.

    Legacy platelet/plasma rows become empty placeholders for missing supported components;
    their non-RBC quantities are never relabelled as usable blood. Existing bank, hospital,
    request, and supported inventory records are retained. The complete operation is atomic.
    """
    columns = {column["name"] for column in inspect(engine).get_columns("blood_inventory")}
    required = {"blood_bank_id", "blood_group", "component_type", "available_units", "reserved_units", "last_updated", "expiry_date", "availability_status"}
    if not required.issubset(columns):
        return {"skipped": True, "reason": "blood_inventory table absent or not in expected schema"}
    with engine.begin() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM blood_inventory")).scalar_one()
        unsupported = conn.execute(text("SELECT COUNT(*) FROM blood_inventory WHERE component_type NOT IN ('whole_blood','packed_red_blood_cells')")).scalar_one()
        banks = [row[0] for row in conn.execute(text("SELECT id FROM blood_banks ORDER BY id")).all()]
        expiry = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        for bank_id in banks:
            for group in GROUPS:
                rows = conn.execute(text("SELECT id,component_type FROM blood_inventory WHERE blood_bank_id=:bank AND blood_group=:group ORDER BY id"), {"bank": bank_id, "group": group}).all()
                by_component = {component: [] for component in SUPPORTED}
                legacy = []
                for row_id, component in rows:
                    (by_component[component] if component in by_component else legacy).append(row_id)
                if any(len(ids) > 1 for ids in by_component.values()):
                    raise RuntimeError(f"Cannot safely migrate duplicate inventory rows for bank={bank_id}, group={group}")
                for row_id in legacy:
                    missing = next((component for component in SUPPORTED if not by_component[component]), None)
                    if missing is None:
                        conn.execute(text("DELETE FROM blood_inventory WHERE id=:id"), {"id": row_id})
                        continue
                    conn.execute(text("UPDATE blood_inventory SET component_type=:component, available_units=0, reserved_units=0, availability_status='out_of_stock', last_updated=:now WHERE id=:id"), {"component": missing, "now": now, "id": row_id})
                    by_component[missing].append(row_id)
                for component in SUPPORTED:
                    if by_component[component]:
                        continue
                    conn.execute(text("INSERT INTO blood_inventory (blood_bank_id,blood_group,component_type,available_units,reserved_units,last_updated,expiry_date,availability_status) VALUES (:bank,:group,:component,0,0,:now,:expiry,'out_of_stock')"), {"bank": bank_id, "group": group, "component": component, "now": now, "expiry": expiry})
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_bank_group_component ON blood_inventory (blood_bank_id,blood_group,component_type)"))
        after = conn.execute(text("SELECT COUNT(*) FROM blood_inventory")).scalar_one()
        remaining = conn.execute(text("SELECT COUNT(*) FROM blood_inventory WHERE component_type NOT IN ('whole_blood','packed_red_blood_cells')")).scalar_one()
    return {"before": before, "after": after, "legacy_rows_normalized": unsupported, "unsupported_rows_remaining": remaining, "banks": len(banks)}


def migrate_bank_notification_tokens(engine):
    """Add an expiry column for hashed response tokens without touching records."""
    inspector = inspect(engine)
    if "blood_bank_notifications" not in inspector.get_table_names():
        return {"skipped": True, "reason": "blood_bank_notifications table absent"}
    columns = {column["name"] for column in inspector.get_columns("blood_bank_notifications")}
    with engine.begin() as conn:
        if "response_token_expires_at" not in columns:
            conn.execute(text("ALTER TABLE blood_bank_notifications ADD COLUMN response_token_expires_at DATETIME NULL"))
        count = conn.execute(text("SELECT COUNT(*) FROM blood_bank_notifications")).scalar_one()
    return {"blood_bank_notification_records_preserved": count}
