"""Safe, append-only activity projection for transaction observability."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActivityPhase(StrEnum):
    INTENT = "INTENT"
    DISCOVERY = "DISCOVERY"
    CHECKOUT = "CHECKOUT"
    APPROVAL = "APPROVAL"
    PAYMENT = "PAYMENT"
    ORDER = "ORDER"
    FULFILLMENT = "FULFILLMENT"
    RESOLUTION = "RESOLUTION"
    SYSTEM = "SYSTEM"


class ActivityStatus(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    WAITING = "WAITING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INFO = "INFO"


class TransactionActivity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    sequence: int = Field(ge=1)
    transaction_id: str
    kind: str
    phase: ActivityPhase
    status: ActivityStatus
    title: str
    message: str
    actor_type: str
    actor_id: str
    authority: str
    occurred_at: datetime
    data: dict[str, Any] = Field(default_factory=dict)


class TransactionActivityLog:
    """Thread-safe in-memory timeline; replaceable by a durable repository."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._events: dict[str, list[TransactionActivity]] = defaultdict(list)
        self._lock = RLock()

    def record(
        self,
        *,
        transaction_id: str,
        kind: str,
        phase: ActivityPhase,
        status: ActivityStatus,
        title: str,
        message: str,
        actor_type: str,
        actor_id: str,
        authority: str,
        data: dict[str, Any] | None = None,
    ) -> TransactionActivity:
        with self._lock:
            sequence = len(self._events[transaction_id]) + 1
            activity = TransactionActivity(
                event_id=f"{transaction_id}:activity:{sequence}",
                sequence=sequence,
                transaction_id=transaction_id,
                kind=kind,
                phase=phase,
                status=status,
                title=title,
                message=message,
                actor_type=actor_type,
                actor_id=actor_id,
                authority=authority,
                occurred_at=self._clock(),
                data=data or {},
            )
            self._events[transaction_id].append(activity)
            return activity

    def list(self, transaction_id: str, *, after_sequence: int = 0) -> list[TransactionActivity]:
        with self._lock:
            return [
                event.model_copy(deep=True)
                for event in self._events.get(transaction_id, [])
                if event.sequence > after_sequence
            ]


class ActivityReporter:
    """Transaction-bound writer passed into model and MCP lifecycle hooks."""

    def __init__(
        self,
        log: TransactionActivityLog,
        transaction_id: str,
        agent_id: str,
    ) -> None:
        self.log = log
        self.transaction_id = transaction_id
        self.agent_id = agent_id

    def record(
        self,
        *,
        kind: str,
        phase: ActivityPhase,
        status: ActivityStatus,
        title: str,
        message: str,
        authority: str = "agent",
        data: dict[str, Any] | None = None,
    ) -> TransactionActivity:
        return self.log.record(
            transaction_id=self.transaction_id,
            kind=kind,
            phase=phase,
            status=status,
            title=title,
            message=message,
            actor_type="agent",
            actor_id=self.agent_id,
            authority=authority,
            data=data,
        )
