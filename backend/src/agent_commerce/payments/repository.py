"""Payment repository contracts and in-memory implementation."""

from __future__ import annotations

from contextlib import AbstractContextManager
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol

from agent_commerce.commerce.errors import CommerceError
from agent_commerce.payments.models import PaymentCredential, PaymentRecord, RefundRecord


class PaymentRepository(Protocol):
    def atomic(self) -> AbstractContextManager[None]: ...

    def get_credential(self, credential_id: str) -> PaymentCredential | None: ...

    def save_credential(self, credential: PaymentCredential) -> None: ...

    def list_credentials(self, approval_id: str | None = None) -> list[PaymentCredential]: ...

    def get_payment(self, payment_id: str) -> PaymentRecord | None: ...

    def save_payment(self, payment: PaymentRecord) -> None: ...

    def list_payments(self, approval_id: str | None = None) -> list[PaymentRecord]: ...

    def get_refund(self, refund_id: str) -> RefundRecord | None: ...

    def save_refund(self, refund: RefundRecord) -> None: ...

    def get_idempotent(self, operation: str, key: str, fingerprint: str) -> Any | None: ...

    def save_idempotent(self, operation: str, key: str, fingerprint: str, value: Any) -> None: ...


@dataclass
class InMemoryPaymentRepository:
    credentials: dict[str, PaymentCredential] = field(default_factory=dict)
    payments: dict[str, PaymentRecord] = field(default_factory=dict)
    refunds: dict[str, RefundRecord] = field(default_factory=dict)
    idempotency: dict[tuple[str, str], tuple[str, Any]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def atomic(self) -> AbstractContextManager[None]:
        return self._lock

    def get_credential(self, credential_id: str) -> PaymentCredential | None:
        value = self.credentials.get(credential_id)
        return deepcopy(value) if value else None

    def save_credential(self, credential: PaymentCredential) -> None:
        self.credentials[credential.credential_id] = deepcopy(credential)

    def list_credentials(self, approval_id: str | None = None) -> list[PaymentCredential]:
        values = list(self.credentials.values())
        if approval_id is not None:
            values = [item for item in values if item.approval_id == approval_id]
        return deepcopy(values)

    def get_payment(self, payment_id: str) -> PaymentRecord | None:
        value = self.payments.get(payment_id)
        return deepcopy(value) if value else None

    def save_payment(self, payment: PaymentRecord) -> None:
        self.payments[payment.payment_id] = deepcopy(payment)

    def list_payments(self, approval_id: str | None = None) -> list[PaymentRecord]:
        values = list(self.payments.values())
        if approval_id is not None:
            values = [item for item in values if item.approval_id == approval_id]
        return deepcopy(values)

    def get_refund(self, refund_id: str) -> RefundRecord | None:
        value = self.refunds.get(refund_id)
        return deepcopy(value) if value else None

    def save_refund(self, refund: RefundRecord) -> None:
        self.refunds[refund.refund_id] = deepcopy(refund)

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
