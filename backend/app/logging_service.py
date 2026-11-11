import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.models import SystemLog
from app.security import sanitize_dict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("rajon.host")


class ExecutionMonitorHub:
    """In-memory ring buffer and WebSocket broadcaster for the Host Execution Monitor."""

    def __init__(self, max_events: int = 500):
        self.max_events = max_events
        self.events: List[Dict[str, Any]] = []
        self.connections: List[asyncio.Queue] = []

    def publish(self, event: Dict[str, Any]) -> None:
        self.events.insert(0, event)
        if len(self.events) > self.max_events:
            self.events = self.events[: self.max_events]
        for q in list(self.connections):
            try:
                q.put_nowait(event)
            except Exception:
                pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.connections.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self.connections:
            self.connections.remove(q)


monitor_hub = ExecutionMonitorHub()


def record_system_log(
    db: Session,
    severity: str,
    component: str,
    event_name: str,
    message: str,
    transaction_id: Optional[str] = None,
    operation_reference: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    commit: bool = False,
) -> SystemLog:
    sanitized = sanitize_dict(details or {})
    log_entry = SystemLog(
        severity=severity.upper(),
        component=component,
        event_name=event_name,
        message=message,
        transaction_id=transaction_id,
        operation_reference=operation_reference,
        sanitized_details=sanitized,
    )
    db.add(log_entry)
    if commit:
        db.commit()
        db.refresh(log_entry)
    else:
        db.flush()

    event_payload = {
        "id": log_entry.id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity.upper(),
        "component": component,
        "event_name": event_name,
        "message": message,
        "transaction_id": transaction_id,
        "operation_reference": operation_reference,
        "sanitized_details": sanitized,
    }
    monitor_hub.publish(event_payload)
    logger.info("[%s:%s] %s", component, event_name, message)
    return log_entry
