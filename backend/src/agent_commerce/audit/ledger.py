"""Thread-safe append-only audit ledger for the hackathon baseline."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from agent_commerce.audit.models import AuditEvent


class AuditLedger:
    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self._events: list[AuditEvent] = []
        self._lock = RLock()

    def record(
        self,
        *,
        transaction_id: str,
        action: str,
        actor_type: str,
        actor_id: str,
        subject_type: str,
        subject_id: str,
        data: dict[str, object] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            audit_event_id=f"audit_{self._id_factory()}",
            occurred_at=self._clock(),
            transaction_id=transaction_id,
            correlation_id=transaction_id,
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            subject_type=subject_type,
            subject_id=subject_id,
            data=data or {},
        )
        with self._lock:
            self._events.append(event)
        return event

    def list_events(self, transaction_id: str | None = None) -> list[AuditEvent]:
        with self._lock:
            events = self._events
            if transaction_id is not None:
                events = [event for event in events if event.transaction_id == transaction_id]
            return deepcopy(events)

