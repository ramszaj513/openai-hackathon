"""Provider adapter contract and deterministic simulator implementation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from agent_commerce.commerce.errors import CommerceError, conflict, not_found
from agent_commerce.payments.models import (
    PaymentCredential,
    PaymentRecord,
    PaymentScenario,
    PaymentStatus,
    RefundRecord,
    RefundStatus,
)
from agent_commerce.payments.repository import PaymentRepository


class PaymentAdapter(Protocol):
    name: str

    def authorize(
        self,
        credential: PaymentCredential,
        *,
        scenario: PaymentScenario,
        payment_id: str,
    ) -> PaymentRecord: ...

    def capture(
        self, payment_id: str, order_id: str, amount_minor: int
    ) -> PaymentRecord: ...

    def void(self, payment_id: str) -> PaymentRecord: ...

    def refund(
        self,
        payment_id: str,
        order_id: str,
        amount_minor: int,
        reason: str,
        refund_id: str,
    ) -> tuple[PaymentRecord, RefundRecord]: ...


class SimulatorPaymentAdapter:
    name = "simulator"

    def __init__(
        self,
        repository: PaymentRepository,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self._clock = clock

    def authorize(
        self,
        credential: PaymentCredential,
        *,
        scenario: PaymentScenario,
        payment_id: str,
    ) -> PaymentRecord:
        now = self._clock()
        status = (
            PaymentStatus.DECLINED
            if scenario is PaymentScenario.DECLINE
            else PaymentStatus.AUTHORIZED
        )
        payment = PaymentRecord(
            payment_id=payment_id,
            provider=self.name,
            provider_reference=f"sim_{payment_id}",
            transaction_id=credential.transaction_id,
            approval_id=credential.approval_id,
            credential_id=credential.credential_id,
            merchant_id=credential.merchant_id,
            checkout_id=credential.checkout_id,
            checkout_version=credential.checkout_version,
            status=status,
            authorized_amount_minor=(
                credential.max_amount_minor if status is PaymentStatus.AUTHORIZED else 0
            ),
            captured_amount_minor=0,
            refunded_amount_minor=0,
            currency=credential.currency,
            created_at=now,
            updated_at=now,
        )
        self.repository.save_payment(payment)
        return payment

    def capture(self, payment_id: str, order_id: str, amount_minor: int) -> PaymentRecord:
        payment = self.repository.get_payment(payment_id)
        if payment is None:
            raise not_found("payment", payment_id)
        if payment.status is PaymentStatus.CAPTURED and payment.order_id == order_id:
            return payment
        if payment.status is not PaymentStatus.AUTHORIZED:
            raise conflict("Only an authorized payment can be captured", status=payment.status)
        if amount_minor != payment.authorized_amount_minor:
            raise CommerceError(
                code="PAYMENT_DECLINED",
                message="Capture amount must match the authorized amount",
            )
        captured = payment.model_copy(
            update={
                "status": PaymentStatus.CAPTURED,
                "captured_amount_minor": amount_minor,
                "order_id": order_id,
                "updated_at": self._clock(),
            }
        )
        self.repository.save_payment(captured)
        return captured

    def void(self, payment_id: str) -> PaymentRecord:
        payment = self.repository.get_payment(payment_id)
        if payment is None:
            raise not_found("payment", payment_id)
        if payment.status is PaymentStatus.VOIDED:
            return payment
        if payment.status is not PaymentStatus.AUTHORIZED:
            raise conflict("Only an authorized payment can be voided", status=payment.status)
        voided = payment.model_copy(
            update={"status": PaymentStatus.VOIDED, "updated_at": self._clock()}
        )
        self.repository.save_payment(voided)
        return voided

    def refund(
        self,
        payment_id: str,
        order_id: str,
        amount_minor: int,
        reason: str,
        refund_id: str,
    ) -> tuple[PaymentRecord, RefundRecord]:
        payment = self.repository.get_payment(payment_id)
        if payment is None:
            raise not_found("payment", payment_id)
        if payment.order_id != order_id:
            raise CommerceError(code="PAYMENT_DECLINED", message="Refund order mismatch")
        if payment.status not in {
            PaymentStatus.CAPTURED,
            PaymentStatus.PARTIALLY_REFUNDED,
        }:
            raise conflict("Payment is not refundable", status=payment.status)
        refundable = payment.captured_amount_minor - payment.refunded_amount_minor
        if amount_minor > refundable:
            raise CommerceError(
                code="PAYMENT_DECLINED",
                message="Refund exceeds the remaining captured amount",
            )
        total_refunded = payment.refunded_amount_minor + amount_minor
        status = (
            PaymentStatus.REFUNDED
            if total_refunded == payment.captured_amount_minor
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        now = self._clock()
        updated = payment.model_copy(
            update={
                "status": status,
                "refunded_amount_minor": total_refunded,
                "updated_at": now,
            }
        )
        refund = RefundRecord(
            refund_id=refund_id,
            payment_id=payment.payment_id,
            order_id=order_id,
            transaction_id=payment.transaction_id,
            amount_minor=amount_minor,
            currency=payment.currency,
            reason=reason,
            status=RefundStatus.COMPLETED,
            provider_reference=f"sim_{refund_id}",
            created_at=now,
        )
        self.repository.save_payment(updated)
        self.repository.save_refund(refund)
        return updated, refund

