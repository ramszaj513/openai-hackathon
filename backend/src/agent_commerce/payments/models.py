"""Typed payment credential, authorization, receipt, and refund contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from agent_commerce.commerce.models import PaymentAuthorizationReference


class PaymentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CredentialStatus(StrEnum):
    ISSUED = "ISSUED"
    CONSUMED = "CONSUMED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class PaymentStatus(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    VOIDED = "VOIDED"
    DECLINED = "DECLINED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"


class RefundStatus(StrEnum):
    COMPLETED = "COMPLETED"


class PaymentScenario(StrEnum):
    APPROVE = "APPROVE"
    DECLINE = "DECLINE"


class IssuePaymentCredentialRequest(PaymentModel):
    approval_id: str
    user_id: str
    idempotency_key: str


class PaymentCredential(PaymentModel):
    credential_id: str
    approval_id: str
    transaction_id: str
    user_id: str
    merchant_id: str
    checkout_id: str
    checkout_version: int
    max_amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: CredentialStatus
    single_use: bool = True
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class AuthorizePaymentRequest(PaymentModel):
    credential_id: str
    approval_id: str
    scenario: PaymentScenario = PaymentScenario.APPROVE
    idempotency_key: str


class PaymentRecord(PaymentModel):
    payment_id: str
    provider: str
    provider_reference: str
    transaction_id: str
    approval_id: str
    credential_id: str
    merchant_id: str
    checkout_id: str
    checkout_version: int
    status: PaymentStatus
    authorized_amount_minor: int
    captured_amount_minor: int
    refunded_amount_minor: int
    currency: str
    order_id: str | None = None
    created_at: datetime
    updated_at: datetime


class AuthorizationResult(PaymentModel):
    payment: PaymentRecord
    merchant_reference: PaymentAuthorizationReference | None


class CapturePaymentRequest(PaymentModel):
    payment_id: str
    order_id: str
    amount_minor: int | None = Field(default=None, gt=0)
    idempotency_key: str


class VoidPaymentRequest(PaymentModel):
    payment_id: str
    reason: str = Field(min_length=1)
    idempotency_key: str


class RefundPaymentRequest(PaymentModel):
    payment_id: str
    order_id: str
    amount_minor: int = Field(gt=0)
    reason: str = Field(min_length=1)
    idempotency_key: str


class RefundRecord(PaymentModel):
    refund_id: str
    payment_id: str
    order_id: str
    transaction_id: str
    amount_minor: int
    currency: str
    reason: str
    status: RefundStatus
    provider_reference: str
    created_at: datetime


class PaymentReceipt(PaymentModel):
    payment_id: str
    approval_id: str
    transaction_id: str
    order_id: str | None
    authorized_amount_minor: int
    captured_amount_minor: int
    refunded_amount_minor: int
    currency: str
    status: PaymentStatus
    provider_reference: str
    occurred_at: datetime


class RecoverAuthorizationRequest(PaymentModel):
    payment_id: str
    reconciled_order_id: str | None = None
    idempotency_key: str


class RecoveryResult(PaymentModel):
    action: str
    payment: PaymentRecord
    receipt: PaymentReceipt

