"""Typed trust, consent, mandate, and approval contracts."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from agent_commerce.commerce.models import (
    CheckoutLine,
    DeliveryOption,
    PriceBreakdown,
    ReturnPolicy,
)


class TrustModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MandateStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class ProposalStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class ApprovalStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class ApprovalSource(StrEnum):
    EXPLICIT_USER = "EXPLICIT_USER"
    SPENDING_MANDATE = "SPENDING_MANDATE"


class PolicyOutcome(StrEnum):
    AUTO_APPROVED = "AUTO_APPROVED"
    EXPLICIT_APPROVAL_REQUIRED = "EXPLICIT_APPROVAL_REQUIRED"
    DENIED = "DENIED"


class CreateSpendingMandateRequest(TrustModel):
    user_id: str
    agent_id: str
    allowed_merchant_ids: frozenset[str] = Field(default_factory=frozenset)
    allowed_categories: frozenset[str] = Field(default_factory=frozenset)
    max_transaction_minor: int = Field(gt=0)
    max_total_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    minimum_return_window_days: int = Field(default=0, ge=0)
    latest_delivery_date: date | None = None
    requires_final_approval: bool = False
    valid_from: datetime
    expires_at: datetime
    idempotency_key: str


class SpendingMandate(TrustModel):
    mandate_id: str
    user_id: str
    agent_id: str
    allowed_merchant_ids: frozenset[str]
    allowed_categories: frozenset[str]
    max_transaction_minor: int
    max_total_minor: int
    used_amount_minor: int
    reserved_amount_minor: int
    currency: str
    minimum_return_window_days: int
    latest_delivery_date: date | None
    requires_final_approval: bool
    status: MandateStatus
    valid_from: datetime
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class CreateCheckoutProposalRequest(TrustModel):
    checkout_id: str
    user_id: str
    agent_id: str
    selection_reason: str = Field(min_length=3)
    satisfied_constraints: tuple[str, ...] = ()
    disclosed_compromises: tuple[str, ...] = ()
    idempotency_key: str


class CheckoutProposal(TrustModel):
    proposal_id: str
    transaction_id: str
    checkout_id: str
    checkout_version: int
    merchant_id: str
    user_id: str
    agent_id: str
    lines: tuple[CheckoutLine, ...]
    delivery_option: DeliveryOption
    price: PriceBreakdown
    return_policy: ReturnPolicy
    selection_reason: str
    satisfied_constraints: tuple[str, ...]
    disclosed_compromises: tuple[str, ...]
    content_hash: str
    status: ProposalStatus
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class EvaluateProposalRequest(TrustModel):
    proposal_id: str
    user_id: str
    agent_id: str
    mandate_id: str | None = None
    idempotency_key: str


class ExplicitApprovalRequest(TrustModel):
    proposal_id: str
    user_id: str
    approved_content_hash: str
    mandate_id: str | None = None
    idempotency_key: str


class RejectProposalRequest(TrustModel):
    proposal_id: str
    user_id: str
    reason: str = Field(min_length=1)
    idempotency_key: str


class RevokeMandateRequest(TrustModel):
    mandate_id: str
    user_id: str
    idempotency_key: str


class ApprovalRecord(TrustModel):
    approval_id: str
    proposal_id: str
    transaction_id: str
    checkout_id: str
    checkout_version: int
    merchant_id: str
    user_id: str
    agent_id: str
    amount_minor: int
    currency: str
    proposal_hash: str
    source: ApprovalSource
    mandate_id: str | None
    status: ApprovalStatus
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class PolicyDecision(TrustModel):
    outcome: PolicyOutcome
    reasons: tuple[str, ...]
    proposal: CheckoutProposal
    approval: ApprovalRecord | None = None
