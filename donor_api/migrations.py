"""Idempotent additions for persistent donor notification response/delivery state."""
from sqlalchemy import inspect, text


_ADDITIONS = {
    "blood_request_id": "INTEGER NULL",
    "blood_group": "VARCHAR(3) NULL",
    "delivery_status": "VARCHAR(16) NOT NULL DEFAULT 'simulated'",
    "response_status": "VARCHAR(24) NOT NULL DEFAULT 'pending'",
    "sent_at": "DATETIME NULL",
    "delivered_at": "DATETIME NULL",
    "response_at": "DATETIME NULL",
    "error_details": "TEXT NULL",
    "idempotency_key": "VARCHAR(160) NULL",
    "response_token_hash": "VARCHAR(64) NULL",
    "response_token_expires_at": "DATETIME NULL",
}


def migrate_donor_notifications(engine):
    with engine.begin() as conn:
        columns = {column["name"] for column in inspect(conn).get_columns("donor_notifications")}
        legacy_schema = "delivery_status" not in columns
        for name, ddl in _ADDITIONS.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE donor_notifications ADD COLUMN {name} {ddl}"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_donor_notification_request_status ON donor_notifications (blood_request_id,delivery_status)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_donor_notification_idempotency_key ON donor_notifications (idempotency_key)"))
        if legacy_schema:
            # Old records came from a synthetic log and cannot be represented as real delivery.
            conn.execute(text("UPDATE donor_notifications SET delivery_status='simulated',response_status='pending',sent_at=NULL,delivered_at=NULL,response_at=NULL,response=NULL,error_details='Legacy synthetic notification; delivery was not verified'"))
            conn.execute(text("UPDATE donor_notifications SET delivery_status='failed',error_details='Blocked because the donor had not consented' WHERE consent_at_attempt=0"))
        count = conn.execute(text("SELECT COUNT(*) FROM donor_notifications")).scalar_one()
    return {"donor_notification_records_preserved": count}
