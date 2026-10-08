"""Audit logging middleware and persistence utility (Part 15)."""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.auth.models import AuditLog

logger = logging.getLogger("AuditLogger")


def record_audit_log(
    db: Session,
    action: str,
    resource: str,
    resource_id: Optional[int] = None,
    user_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Record an audit trail entry in the database.
    
    Args:
        db: Active SQLAlchemy database session.
        action: Operational action (e.g. 'CREATE_REQUEST', 'UPDATE_STATUS', 'COORDINATE').
        resource: Resource type ('blood_request', 'user', 'hospital').
        resource_id: Identifier of the primary resource entity.
        user_id: ID of the user performing the action, or None if anonymous/system.
        details: Additional context dictionary serialized as JSON.
        
    Returns:
        Created and committed AuditLog model instance.
    """
    serialized_details = json.dumps(details or {})
    log_entry = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        timestamp=datetime.now(timezone.utc),
        details=serialized_details,
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    logger.info(f"[AUDIT] User #{user_id} performed '{action}' on {resource} #{resource_id}")
    return log_entry
