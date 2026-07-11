"""Audit contracts for trust and payment actions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_event_id: str
    occurred_at: datetime
    transaction_id: str
    correlation_id: str
    action: str
    actor_type: str
    actor_id: str
    subject_type: str
    subject_id: str
    data: dict[str, Any]
