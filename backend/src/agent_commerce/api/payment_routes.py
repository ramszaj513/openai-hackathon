"""Scoped credential and payment lifecycle REST routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_commerce.audit.models import AuditEvent
from agent_commerce.payments.models import (
    AuthorizationResult,
    AuthorizePaymentRequest,
    CapturePaymentRequest,
    IssuePaymentCredentialRequest,
    PaymentCredential,
    PaymentReceipt,
    PaymentRecord,
    RecoverAuthorizationRequest,
    RecoveryResult,
    RefundPaymentRequest,
    RefundRecord,
    VoidPaymentRequest,
)
from agent_commerce.payments.service import PaymentService


def create_payment_router(payment_service: PaymentService) -> APIRouter:
    router = APIRouter(prefix="/api/payments", tags=["payments"])

    def get_payments() -> PaymentService:
        return payment_service

    Payments = Depends(get_payments)

    @router.post("/credentials", response_model=PaymentCredential, status_code=201)
    def issue_credential(
        request: IssuePaymentCredentialRequest,
        payments: PaymentService = Payments,
    ) -> PaymentCredential:
        return payments.issue_credential(request)

    @router.get("/credentials/{credential_id}", response_model=PaymentCredential)
    def get_credential(
        credential_id: str, payments: PaymentService = Payments
    ) -> PaymentCredential:
        return payments.get_credential(credential_id)

    @router.post("/authorize", response_model=AuthorizationResult)
    def authorize(
        request: AuthorizePaymentRequest,
        payments: PaymentService = Payments,
    ) -> AuthorizationResult:
        return payments.authorize(request)

    @router.get("/{payment_id}", response_model=PaymentRecord)
    def get_payment(payment_id: str, payments: PaymentService = Payments) -> PaymentRecord:
        return payments.get_payment(payment_id)

    @router.post("/{payment_id}/capture", response_model=PaymentReceipt)
    def capture(
        payment_id: str,
        request: CapturePaymentRequest,
        payments: PaymentService = Payments,
    ) -> PaymentReceipt:
        _validate_payment_path(payment_id, request.payment_id)
        return payments.capture(request)

    @router.post("/{payment_id}/void", response_model=PaymentReceipt)
    def void(
        payment_id: str,
        request: VoidPaymentRequest,
        payments: PaymentService = Payments,
    ) -> PaymentReceipt:
        _validate_payment_path(payment_id, request.payment_id)
        return payments.void(request)

    @router.post("/{payment_id}/refunds", response_model=RefundRecord, status_code=201)
    def refund(
        payment_id: str,
        request: RefundPaymentRequest,
        payments: PaymentService = Payments,
    ) -> RefundRecord:
        _validate_payment_path(payment_id, request.payment_id)
        return payments.refund(request)

    @router.post("/{payment_id}/recover", response_model=RecoveryResult)
    def recover(
        payment_id: str,
        request: RecoverAuthorizationRequest,
        payments: PaymentService = Payments,
    ) -> RecoveryResult:
        _validate_payment_path(payment_id, request.payment_id)
        return payments.recover_authorization(request)

    @router.get("/transactions/{transaction_id}/audit", response_model=list[AuditEvent])
    def list_audit(
        transaction_id: str, payments: PaymentService = Payments
    ) -> list[AuditEvent]:
        return payments.audit.list_events(transaction_id)

    return router


def _validate_payment_path(path_payment_id: str, request_payment_id: str) -> None:
    if path_payment_id != request_payment_id:
        from agent_commerce.commerce.errors import validation_error

        raise validation_error("Path payment_id does not match request payment_id")

