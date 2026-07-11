"""Payment credential and lifecycle service with safe recovery semantics."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel

from agent_commerce.audit import AuditLedger
from agent_commerce.commerce.errors import CommerceError, conflict, not_found
from agent_commerce.commerce.models import PaymentAuthorizationReference
from agent_commerce.payments.adapter import PaymentAdapter, SimulatorPaymentAdapter
from agent_commerce.payments.models import (
    AuthorizationResult,
    AuthorizePaymentRequest,
    CapturePaymentRequest,
    CredentialStatus,
    IssuePaymentCredentialRequest,
    PaymentCredential,
    PaymentReceipt,
    PaymentRecord,
    PaymentStatus,
    RecoverAuthorizationRequest,
    RecoveryResult,
    RefundPaymentRequest,
    RefundRecord,
    RefundStatus,
    VoidPaymentRequest,
)
from agent_commerce.payments.repository import (
    InMemoryPaymentRepository,
    PaymentRepository,
)
from agent_commerce.payments.settings import PaymentProvider, PaymentSettings
from agent_commerce.trust import TrustService
from agent_commerce.trust.models import ApprovalStatus

ModelT = TypeVar("ModelT", bound=BaseModel)


class PaymentService:
    def __init__(
        self,
        trust: TrustService,
        repository: PaymentRepository | None = None,
        audit: AuditLedger | None = None,
        adapter: PaymentAdapter | None = None,
        settings: PaymentSettings | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.trust = trust
        self.repository = repository or InMemoryPaymentRepository()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self.audit = audit or trust.audit
        if adapter is not None:
            self.adapter = adapter
        elif settings is not None and settings.payment_provider is PaymentProvider.STRIPE:
            from agent_commerce.payments.stripe_adapter import StripePaymentAdapter

            if settings.stripe_secret_key is None:  # Guarded by PaymentSettings validation.
                raise RuntimeError("Stripe secret key is missing")
            self.adapter = StripePaymentAdapter(
                self.repository,
                clock=self._clock,
                secret_key=settings.stripe_secret_key.get_secret_value(),
                payment_method=settings.stripe_payment_method,
                decline_payment_method=settings.stripe_decline_payment_method,
                api_base=settings.stripe_api_base,
                timeout_seconds=settings.stripe_timeout_seconds,
            )
        else:
            self.adapter = SimulatorPaymentAdapter(
                self.repository,
                clock=self._clock,
            )

    def issue_credential(self, request: IssuePaymentCredentialRequest) -> PaymentCredential:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "issue_credential", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, PaymentCredential)
            approval = self.trust.get_approval(request.approval_id)
            evidence = self.trust.get_approval_evidence(request.approval_id)
            if approval.user_id != request.user_id:
                raise CommerceError(code="APPROVAL_INVALID", message="Credential user mismatch")
            if any(
                item.status is CredentialStatus.ISSUED
                for item in self.repository.list_credentials(approval.approval_id)
            ):
                raise conflict("An active credential already exists for this approval")
            if any(
                item.status in {PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED}
                for item in self.repository.list_payments(approval.approval_id)
            ):
                raise conflict("Approval already has an active or captured payment")
            now = self._now()
            credential = PaymentCredential(
                credential_id=f"credential_{self._id_factory()}",
                approval_id=approval.approval_id,
                transaction_id=approval.transaction_id,
                user_id=approval.user_id,
                merchant_id=evidence.merchant_id,
                checkout_id=evidence.checkout_id,
                checkout_version=evidence.checkout_version,
                max_amount_minor=evidence.amount_minor,
                currency=evidence.currency,
                status=CredentialStatus.ISSUED,
                expires_at=evidence.expires_at,
                created_at=now,
                updated_at=now,
            )
            self.repository.save_credential(credential)
            self.repository.save_idempotent(
                "issue_credential", request.idempotency_key, fingerprint, credential
            )
            self.audit.record(
                transaction_id=credential.transaction_id,
                action="payment_credential.issued",
                actor_type="payment_service",
                actor_id=self.adapter.name,
                subject_type="payment_credential",
                subject_id=credential.credential_id,
                data={
                    "merchant_id": credential.merchant_id,
                    "checkout_id": credential.checkout_id,
                    "checkout_version": credential.checkout_version,
                    "max_amount_minor": credential.max_amount_minor,
                    "currency": credential.currency,
                    "single_use": credential.single_use,
                },
            )
            return credential

    def get_credential(self, credential_id: str) -> PaymentCredential:
        credential = self.repository.get_credential(credential_id)
        if credential is None:
            raise not_found("payment_credential", credential_id)
        if credential.status is CredentialStatus.ISSUED and credential.expires_at <= self._now():
            expired = credential.model_copy(
                update={"status": CredentialStatus.EXPIRED, "updated_at": self._now()}
            )
            self.repository.save_credential(expired)
            return expired
        return credential

    def authorize(self, request: AuthorizePaymentRequest) -> AuthorizationResult:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "authorize_payment", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, AuthorizationResult)
            credential = self.get_credential(request.credential_id)
            approval = self.trust.get_approval(request.approval_id)
            evidence = self.trust.get_approval_evidence(request.approval_id)
            if credential.status is not CredentialStatus.ISSUED:
                raise CommerceError(
                    code="PAYMENT_DECLINED",
                    message="Payment credential is not available",
                    details={"status": credential.status},
                )
            if credential.approval_id != approval.approval_id:
                raise CommerceError(code="PAYMENT_DECLINED", message="Approval mismatch")
            if approval.status is not ApprovalStatus.APPROVED:
                raise CommerceError(code="PAYMENT_DECLINED", message="Approval is not active")
            expected = {
                "checkout_id": evidence.checkout_id,
                "checkout_version": evidence.checkout_version,
                "merchant_id": evidence.merchant_id,
                "amount_minor": evidence.amount_minor,
                "currency": evidence.currency,
            }
            actual = {
                "checkout_id": credential.checkout_id,
                "checkout_version": credential.checkout_version,
                "merchant_id": credential.merchant_id,
                "amount_minor": credential.max_amount_minor,
                "currency": credential.currency,
            }
            if expected != actual:
                raise CommerceError(
                    code="PAYMENT_DECLINED",
                    message="Credential is not bound to the approved checkout",
                )
            if any(
                item.status in {PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED}
                for item in self.repository.list_payments(approval.approval_id)
            ):
                raise conflict("Approval already has an active or captured payment")
            payment_id = f"pay_{self._id_factory()}"
            payment = self.adapter.authorize(
                credential,
                scenario=request.scenario,
                payment_id=payment_id,
                idempotency_key=request.idempotency_key,
            )
            consumed = credential.model_copy(
                update={"status": CredentialStatus.CONSUMED, "updated_at": self._now()}
            )
            self.repository.save_credential(consumed)
            merchant_reference = None
            if payment.status is PaymentStatus.AUTHORIZED:
                merchant_reference = PaymentAuthorizationReference(
                    payment_authorization_id=payment.payment_id,
                    checkout_id=payment.checkout_id,
                    checkout_version=payment.checkout_version,
                    merchant_id=payment.merchant_id,
                    amount_minor=payment.authorized_amount_minor,
                    currency=payment.currency,
                    expires_at=evidence.expires_at,
                )
            result = AuthorizationResult(
                payment=payment,
                merchant_reference=merchant_reference,
            )
            self.repository.save_idempotent(
                "authorize_payment", request.idempotency_key, fingerprint, result
            )
            self.audit.record(
                transaction_id=payment.transaction_id,
                action=(
                    "payment.authorized"
                    if payment.status is PaymentStatus.AUTHORIZED
                    else "payment.declined"
                ),
                actor_type="payment_provider",
                actor_id=self.adapter.name,
                subject_type="payment",
                subject_id=payment.payment_id,
                data={
                    "amount_minor": payment.authorized_amount_minor,
                    "currency": payment.currency,
                    "merchant_id": payment.merchant_id,
                },
            )
            return result

    def get_payment(self, payment_id: str) -> PaymentRecord:
        payment = self.repository.get_payment(payment_id)
        if payment is None:
            raise not_found("payment", payment_id)
        return payment

    def capture(self, request: CapturePaymentRequest) -> PaymentReceipt:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "capture_payment", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, PaymentReceipt)
            payment = self.get_payment(request.payment_id)
            amount = request.amount_minor or payment.authorized_amount_minor
            captured = self.adapter.capture(
                payment.payment_id,
                request.order_id,
                amount,
                idempotency_key=request.idempotency_key,
            )
            self.trust.record_captured_spend(
                captured.approval_id,
                captured.payment_id,
                captured.captured_amount_minor,
                captured.currency,
            )
            receipt = self._receipt(captured)
            self.repository.save_idempotent(
                "capture_payment", request.idempotency_key, fingerprint, receipt
            )
            self.audit.record(
                transaction_id=captured.transaction_id,
                action="payment.captured",
                actor_type="payment_provider",
                actor_id=self.adapter.name,
                subject_type="payment",
                subject_id=captured.payment_id,
                data={
                    "order_id": request.order_id,
                    "amount_minor": captured.captured_amount_minor,
                    "currency": captured.currency,
                },
            )
            return receipt

    def void(self, request: VoidPaymentRequest) -> PaymentReceipt:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "void_payment", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, PaymentReceipt)
            payment = self.adapter.void(
                request.payment_id,
                idempotency_key=request.idempotency_key,
            )
            self.trust.invalidate_approval(payment.approval_id, reason=request.reason)
            receipt = self._receipt(payment)
            self.repository.save_idempotent(
                "void_payment", request.idempotency_key, fingerprint, receipt
            )
            self.audit.record(
                transaction_id=payment.transaction_id,
                action="payment.voided",
                actor_type="payment_provider",
                actor_id=self.adapter.name,
                subject_type="payment",
                subject_id=payment.payment_id,
                data={"reason": request.reason},
            )
            return receipt

    def refund(self, request: RefundPaymentRequest) -> RefundRecord:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "refund_payment", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, RefundRecord)
            refund_id = f"refund_{self._id_factory()}"
            payment, refund = self.adapter.refund(
                request.payment_id,
                request.order_id,
                request.amount_minor,
                request.reason,
                refund_id,
                idempotency_key=request.idempotency_key,
            )
            if refund.status is RefundStatus.COMPLETED:
                self.trust.record_refund(
                    payment.approval_id,
                    refund.refund_id,
                    refund.amount_minor,
                    refund.currency,
                )
            self.repository.save_idempotent(
                "refund_payment", request.idempotency_key, fingerprint, refund
            )
            self.audit.record(
                transaction_id=payment.transaction_id,
                action={
                    RefundStatus.COMPLETED: "refund.completed",
                    RefundStatus.PENDING: "refund.pending",
                    RefundStatus.FAILED: "refund.failed",
                }[refund.status],
                actor_type="payment_provider",
                actor_id=self.adapter.name,
                subject_type="refund",
                subject_id=refund.refund_id,
                data={
                    "payment_id": payment.payment_id,
                    "order_id": request.order_id,
                    "amount_minor": refund.amount_minor,
                    "currency": refund.currency,
                    "reason": request.reason,
                },
            )
            return refund

    def recover_authorization(self, request: RecoverAuthorizationRequest) -> RecoveryResult:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "recover_authorization", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, RecoveryResult)
            payment = self.get_payment(request.payment_id)
            if payment.status is not PaymentStatus.AUTHORIZED:
                raise conflict(
                    "Only an unresolved authorization can be recovered",
                    status=payment.status,
                )
            if request.reconciled_order_id is not None:
                receipt = self.capture(
                    CapturePaymentRequest(
                        payment_id=payment.payment_id,
                        order_id=request.reconciled_order_id,
                        idempotency_key=f"recovery-capture:{request.idempotency_key}",
                    )
                )
                action = "CAPTURED_EXISTING_ORDER"
            else:
                receipt = self.void(
                    VoidPaymentRequest(
                        payment_id=payment.payment_id,
                        reason="No merchant order exists after reconciliation",
                        idempotency_key=f"recovery-void:{request.idempotency_key}",
                    )
                )
                action = "VOIDED_ORPHAN_AUTHORIZATION"
            result = RecoveryResult(
                action=action,
                payment=self.get_payment(payment.payment_id),
                receipt=receipt,
            )
            self.repository.save_idempotent(
                "recover_authorization", request.idempotency_key, fingerprint, result
            )
            self.audit.record(
                transaction_id=payment.transaction_id,
                action="payment.recovered",
                actor_type="system",
                actor_id="payment-recovery",
                subject_type="payment",
                subject_id=payment.payment_id,
                data={"action": action, "order_id": request.reconciled_order_id},
            )
            return result

    def _receipt(self, payment: PaymentRecord) -> PaymentReceipt:
        return PaymentReceipt(
            payment_id=payment.payment_id,
            approval_id=payment.approval_id,
            transaction_id=payment.transaction_id,
            order_id=payment.order_id,
            authorized_amount_minor=payment.authorized_amount_minor,
            captured_amount_minor=payment.captured_amount_minor,
            refunded_amount_minor=payment.refunded_amount_minor,
            currency=payment.currency,
            status=payment.status,
            provider_reference=payment.provider_reference,
            occurred_at=self._now(),
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise RuntimeError("Payment clock must return a timezone-aware datetime")
        return value

    @staticmethod
    def _fingerprint(request: BaseModel) -> str:
        canonical = request.model_dump_json(exclude={"idempotency_key"})
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _expect_type(value: object, expected: type[ModelT]) -> ModelT:
        if not isinstance(value, expected):
            raise RuntimeError(f"Corrupt idempotency record: expected {expected.__name__}")
        return value
