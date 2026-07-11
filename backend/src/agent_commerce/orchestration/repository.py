"""Transaction repository and idempotency for orchestration commands."""

from __future__ import annotations

from contextlib import AbstractContextManager
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol

from agent_commerce.commerce.errors import CommerceError
from agent_commerce.orchestration.models import AgentTransaction


class TransactionRepository(Protocol):
    def atomic(self) -> AbstractContextManager[bool]: ...

    def get(self, transaction_id: str) -> AgentTransaction | None: ...

    def save(self, transaction: AgentTransaction) -> None: ...

    def get_idempotent(self, operation: str, key: str, fingerprint: str) -> Any | None: ...

    def save_idempotent(self, operation: str, key: str, fingerprint: str, value: Any) -> None: ...


@dataclass
class InMemoryTransactionRepository:
    transactions: dict[str, AgentTransaction] = field(default_factory=dict)
    idempotency: dict[tuple[str, str], tuple[str, Any]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def atomic(self) -> AbstractContextManager[bool]:
        return self._lock

    def get(self, transaction_id: str) -> AgentTransaction | None:
        value = self.transactions.get(transaction_id)
        return deepcopy(value) if value else None

    def save(self, transaction: AgentTransaction) -> None:
        self.transactions[transaction.transaction_id] = deepcopy(transaction)

    def get_idempotent(self, operation: str, key: str, fingerprint: str) -> Any | None:
        stored = self.idempotency.get((operation, key))
        if stored is None:
            return None
        stored_fingerprint, value = stored
        if stored_fingerprint != fingerprint:
            raise CommerceError(
                code="IDEMPOTENCY_CONFLICT",
                message="Idempotency key was reused with a different request",
                details={"operation": operation, "idempotency_key": key},
            )
        return deepcopy(value)

    def save_idempotent(self, operation: str, key: str, fingerprint: str, value: Any) -> None:
        self.idempotency[(operation, key)] = (fingerprint, deepcopy(value))
