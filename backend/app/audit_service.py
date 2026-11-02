"""
audit_service.py — Entity Snapshot and Audit Trail Logger
Captures before/after JSON states and diff summaries for regulatory audit compliance.
"""

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.models import AuditTrail


def serialize_entity(entity: Any) -> Dict[str, Any]:
    """Serialize a SQLAlchemy declarative model into a clean JSON-serializable dict."""
    if entity is None:
        return {}
    out: Dict[str, Any] = {}
    for col in entity.__table__.columns:
        val = getattr(entity, col.name, None)
        if isinstance(val, bool):
            out[col.name] = val
        elif hasattr(val, "isoformat"):
            out[col.name] = val.isoformat()
        elif hasattr(val, "__float__"):
            out[col.name] = float(val)
        else:
            out[col.name] = val
    return out


def record_audit(
    db: Session,
    entity_type: str,
    entity_id: str,
    action: str,
    performed_by: str = "admin",
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
    change_summary: Optional[str] = None,
) -> AuditTrail:
    """Record an immutable audit trail entry."""
    entry = AuditTrail(
        entity_type=entity_type.upper(),
        entity_id=str(entity_id),
        action=action.upper(),
        performed_by=performed_by,
        before_state=before_state,
        after_state=after_state,
        change_summary=change_summary,
    )
    db.add(entry)
    db.flush()
    return entry
