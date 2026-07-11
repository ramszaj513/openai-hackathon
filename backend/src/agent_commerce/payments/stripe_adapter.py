"""Stripe test-mode PaymentIntent adapter with separate authorization and capture."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

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


@dataclass(slots=True)
class _StripeRequestError(Exception):
    status_code: int
    error_type: str | None
    code: str | None
    decline_code: str | None
    payment_intent_id: str | None


class StripePaymentAdapter:
    """Use card PaymentIntents without exposing a client secret or reusable credential."""

    name = "stripe"

    def __init__(
        self,
        repository: PaymentRepository,
        *,
        clock: Callable[[], datetime],
        secret_key: str,
        payment_method: str = "pm_card_visa",
        decline_payment_method: str = "pm_card_visa_chargeDeclined",
        api_base: str = "https://api.stripe.com/v1",
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not secret_key.startswith("sk_test_"):
            raise ValueError("StripePaymentAdapter accepts only a Stripe test-mode secret key")
        self.repository = repository
        self._clock = clock
        self._secret_key = secret_key
        self._payment_method = payment_method
        self._decline_payment_method = decline_payment_method
        self._api_base = api_base.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    def authorize(
        self,
        credential: PaymentCredential,
        *,
        scenario: PaymentScenario,
        payment_id: str,
        idempotency_key: str,
        payment_method_id: str | None = None,
    ) -> PaymentRecord:
        payment_method = (
            self._decline_payment_method
            if scenario is PaymentScenario.DECLINE
            else payment_method_id or self._payment_method
        )
        data = {
            "amount": str(credential.max_amount_minor),
            "currency": credential.currency.lower(),
            "payment_method": payment_method,
            "payment_method_types[]": "card",
            "capture_method": "manual",
            "confirm": "true",
            "error_on_requires_action": "true",
            "metadata[transaction_id]": credential.transaction_id,
            "metadata[approval_id]": credential.approval_id,
            "metadata[checkout_id]": credential.checkout_id,
            "metadata[merchant_id]": credential.merchant_id,
            "metadata[application_payment_id]": payment_id,
        }
        try:
            payload = self._post(
                "/payment_intents",
                data,
                idempotency_key=self._stripe_idempotency_key("authorize", idempotency_key),
            )
        except _StripeRequestError as exc:
            if exc.status_code == 402 or exc.error_type == "card_error":
                declined = self._new_payment(
                    credential,
                    payment_id=payment_id,
                    provider_reference=exc.payment_intent_id or f"declined_{payment_id}",
                    status=PaymentStatus.DECLINED,
                    authorized_amount_minor=0,
                    provider_error_code=exc.code,
                    decline_code=exc.decline_code,
                )
                self.repository.save_payment(declined)
                return declined
            raise self._domain_error(exc, operation="authorization") from None

        provider_reference = self._required_string(payload, "id", "authorization")
        if payload.get("status") != "requires_capture":
            raise CommerceError(
                code="PAYMENT_DECLINED",
                message="Stripe did not authorize the payment for manual capture",
                details={"provider_status": self._safe_status(payload)},
            )
        self._validate_money(payload, credential.max_amount_minor, credential.currency)
        payment = self._new_payment(
            credential,
            payment_id=payment_id,
            provider_reference=provider_reference,
            status=PaymentStatus.AUTHORIZED,
            authorized_amount_minor=credential.max_amount_minor,
        )
        self.repository.save_payment(payment)
        return payment

    def capture(
        self,
        payment_id: str,
        order_id: str,
        amount_minor: int,
        *,
        idempotency_key: str,
    ) -> PaymentRecord:
        payment = self._get_payment(payment_id)
        if payment.status is PaymentStatus.CAPTURED and payment.order_id == order_id:
            return payment
        if payment.status is not PaymentStatus.AUTHORIZED:
            raise conflict("Only an authorized payment can be captured", status=payment.status)
        if amount_minor != payment.authorized_amount_minor:
            raise CommerceError(
                code="PAYMENT_DECLINED",
                message="Capture amount must match the authorized amount",
            )
        try:
            payload = self._post(
                f"/payment_intents/{payment.provider_reference}/capture",
                {
                    "amount_to_capture": str(amount_minor),
                    "metadata[order_id]": order_id,
                },
                idempotency_key=self._stripe_idempotency_key("capture", idempotency_key),
            )
        except _StripeRequestError as exc:
            raise self._domain_error(exc, operation="capture") from None
        if payload.get("status") != "succeeded":
            raise self._recovery_required(payload, "capture")
        self._validate_money(
            payload,
            amount_minor,
            payment.currency,
            amount_field="amount_received",
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

    def void(self, payment_id: str, *, idempotency_key: str) -> PaymentRecord:
        payment = self._get_payment(payment_id)
        if payment.status is PaymentStatus.VOIDED:
            return payment
        if payment.status is not PaymentStatus.AUTHORIZED:
            raise conflict("Only an authorized payment can be voided", status=payment.status)
        try:
            payload = self._post(
                f"/payment_intents/{payment.provider_reference}/cancel",
                {"cancellation_reason": "abandoned"},
                idempotency_key=self._stripe_idempotency_key("void", idempotency_key),
            )
        except _StripeRequestError as exc:
            raise self._domain_error(exc, operation="void") from None
        if payload.get("status") != "canceled":
            raise self._recovery_required(payload, "void")
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
        *,
        idempotency_key: str,
    ) -> tuple[PaymentRecord, RefundRecord]:
        payment = self._get_payment(payment_id)
        if payment.order_id != order_id:
            raise CommerceError(code="PAYMENT_DECLINED", message="Refund order mismatch")
        if payment.status not in {PaymentStatus.CAPTURED, PaymentStatus.PARTIALLY_REFUNDED}:
            raise conflict("Payment is not refundable", status=payment.status)
        refundable = payment.captured_amount_minor - payment.refunded_amount_minor
        if amount_minor > refundable:
            raise CommerceError(
                code="PAYMENT_DECLINED",
                message="Refund exceeds the remaining captured amount",
            )
        try:
            payload = self._post(
                "/refunds",
                {
                    "payment_intent": payment.provider_reference,
                    "amount": str(amount_minor),
                    "reason": "requested_by_customer",
                    "metadata[order_id]": order_id,
                    "metadata[application_refund_id]": refund_id,
                },
                idempotency_key=self._stripe_idempotency_key("refund", idempotency_key),
            )
        except _StripeRequestError as exc:
            raise self._domain_error(exc, operation="refund") from None
        provider_reference = self._required_string(payload, "id", "refund")
        provider_status = self._optional_string(payload.get("status"))
        status_by_provider = {
            "succeeded": RefundStatus.COMPLETED,
            "pending": RefundStatus.PENDING,
            "requires_action": RefundStatus.PENDING,
            "failed": RefundStatus.FAILED,
            "canceled": RefundStatus.FAILED,
        }
        refund_status = (
            status_by_provider.get(provider_status) if provider_status is not None else None
        )
        if refund_status is None:
            raise self._recovery_required(payload, "refund")
        self._validate_money(payload, amount_minor, payment.currency)
        now = self._clock()
        updated = payment
        if refund_status is RefundStatus.COMPLETED:
            total_refunded = payment.refunded_amount_minor + amount_minor
            updated = payment.model_copy(
                update={
                    "status": (
                        PaymentStatus.REFUNDED
                        if total_refunded == payment.captured_amount_minor
                        else PaymentStatus.PARTIALLY_REFUNDED
                    ),
                    "refunded_amount_minor": total_refunded,
                    "updated_at": now,
                }
            )
            self.repository.save_payment(updated)
        refund = RefundRecord(
            refund_id=refund_id,
            payment_id=payment.payment_id,
            order_id=order_id,
            transaction_id=payment.transaction_id,
            amount_minor=amount_minor,
            currency=payment.currency,
            reason=reason,
            status=refund_status,
            provider_reference=provider_reference,
            created_at=now,
        )
        self.repository.save_refund(refund)
        return updated, refund

    def _post(
        self,
        path: str,
        data: Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        headers = {"Idempotency-Key": idempotency_key}
        try:
            if self._client is None:
                response = httpx.post(
                    f"{self._api_base}{path}",
                    data=data,
                    headers=headers,
                    auth=(self._secret_key, ""),
                    timeout=self._timeout_seconds,
                )
            else:
                response = self._client.post(
                    f"{self._api_base}{path}",
                    data=data,
                    headers=headers,
                    auth=(self._secret_key, ""),
                    timeout=self._timeout_seconds,
                )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise CommerceError(
                code="TEMPORARILY_UNAVAILABLE",
                message="Stripe request outcome is unknown; retry with the same idempotency key",
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise CommerceError(
                code="RECOVERY_REQUIRED",
                message="Stripe returned an unreadable response; reconcile before retrying",
            ) from exc
        if not isinstance(payload, dict):
            raise CommerceError(
                code="RECOVERY_REQUIRED",
                message="Stripe returned an unexpected response; reconcile before retrying",
            )
        if response.is_error:
            error = payload.get("error")
            safe_error = error if isinstance(error, dict) else {}
            payment_intent = safe_error.get("payment_intent")
            payment_intent_id = (
                payment_intent.get("id")
                if isinstance(payment_intent, dict)
                else payment_intent
                if isinstance(payment_intent, str)
                else None
            )
            raise _StripeRequestError(
                status_code=response.status_code,
                error_type=self._optional_string(safe_error.get("type")),
                code=self._optional_string(safe_error.get("code")),
                decline_code=self._optional_string(safe_error.get("decline_code")),
                payment_intent_id=payment_intent_id,
            )
        return payload

    def _new_payment(
        self,
        credential: PaymentCredential,
        *,
        payment_id: str,
        provider_reference: str,
        status: PaymentStatus,
        authorized_amount_minor: int,
        provider_error_code: str | None = None,
        decline_code: str | None = None,
    ) -> PaymentRecord:
        now = self._clock()
        return PaymentRecord(
            payment_id=payment_id,
            provider=self.name,
            provider_reference=provider_reference,
            provider_error_code=provider_error_code,
            decline_code=decline_code,
            transaction_id=credential.transaction_id,
            approval_id=credential.approval_id,
            credential_id=credential.credential_id,
            merchant_id=credential.merchant_id,
            checkout_id=credential.checkout_id,
            checkout_version=credential.checkout_version,
            status=status,
            authorized_amount_minor=authorized_amount_minor,
            captured_amount_minor=0,
            refunded_amount_minor=0,
            currency=credential.currency,
            created_at=now,
            updated_at=now,
        )

    def _get_payment(self, payment_id: str) -> PaymentRecord:
        payment = self.repository.get_payment(payment_id)
        if payment is None:
            raise not_found("payment", payment_id)
        return payment

    @staticmethod
    def _validate_money(
        payload: Mapping[str, Any],
        amount_minor: int,
        currency: str,
        *,
        amount_field: str = "amount",
    ) -> None:
        if payload.get(amount_field) != amount_minor or payload.get("currency") != currency.lower():
            raise CommerceError(
                code="RECOVERY_REQUIRED",
                message="Stripe response did not match the expected amount and currency",
            )

    @staticmethod
    def _required_string(payload: Mapping[str, Any], key: str, operation: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise CommerceError(
                code="RECOVERY_REQUIRED",
                message=f"Stripe {operation} response omitted its safe provider reference",
            )
        return value

    @staticmethod
    def _safe_status(payload: Mapping[str, Any]) -> str:
        value = payload.get("status")
        return value if isinstance(value, str) else "unknown"

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _stripe_idempotency_key(operation: str, application_key: str) -> str:
        digest = hashlib.sha256(application_key.encode()).hexdigest()
        return f"acg:{operation}:{digest}"

    @classmethod
    def _recovery_required(cls, payload: Mapping[str, Any], operation: str) -> CommerceError:
        return CommerceError(
            code="RECOVERY_REQUIRED",
            message=f"Stripe {operation} has an unexpected state; reconcile before retrying",
            details={"provider_status": cls._safe_status(payload)},
        )

    @staticmethod
    def _domain_error(error: _StripeRequestError, *, operation: str) -> CommerceError:
        if error.status_code == 429 or error.status_code >= 500:
            return CommerceError(
                code="TEMPORARILY_UNAVAILABLE",
                message=f"Stripe {operation} is temporarily unavailable",
            )
        details = {
            key: value
            for key, value in {
                "provider_code": error.code,
                "decline_code": error.decline_code,
            }.items()
            if value is not None
        }
        return CommerceError(
            code="PAYMENT_DECLINED",
            message=f"Stripe rejected the payment {operation}",
            details=details or None,
        )
