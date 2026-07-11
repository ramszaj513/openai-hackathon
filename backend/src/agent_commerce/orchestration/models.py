"""Typed intent, planning, transaction-state, and orchestration contracts."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from agent_commerce.commerce.models import Checkout, Offer
from agent_commerce.payments.models import PaymentScenario
from agent_commerce.trust.models import CheckoutProposal


class OrchestrationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TransactionState(StrEnum):
    INTENT_CAPTURED = "INTENT_CAPTURED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    DISCOVERING = "DISCOVERING"
    OFFER_SELECTED = "OFFER_SELECTED"
    CHECKOUT_DRAFT = "CHECKOUT_DRAFT"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVED = "APPROVED"
    PAYMENT_AUTHORIZING = "PAYMENT_AUTHORIZING"
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    ORDER_COMMITTING = "ORDER_COMMITTING"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    PAYMENT_CAPTURED = "PAYMENT_CAPTURED"
    FULFILLING = "FULFILLING"
    DELIVERED = "DELIVERED"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    CANCELLED = "CANCELLED"
    RETURN_REQUESTED = "RETURN_REQUESTED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"
    FAILED = "FAILED"


class NormalizedPurchaseIntent(OrchestrationModel):
    product_query: str
    category: str
    quantity: int = Field(default=1, gt=0)
    max_budget_minor: int | None = Field(default=None, gt=0)
    currency: str = Field(default="PLN", pattern=r"^[A-Z]{3}$")
    required_attributes: dict[str, str | bool | int] = Field(default_factory=dict)
    latest_delivery_date: date | None = None
    minimum_return_window_days: int | None = Field(default=None, ge=0)
    purchase_if_confident: bool = False
    missing_required_fields: tuple[str, ...] = ()
    clarification_questions: tuple[str, ...] = ()


class RejectedOffer(OrchestrationModel):
    offer_id: str
    reasons: tuple[str, ...]


class OfferSelectionPlan(OrchestrationModel):
    selected_offer_id: str | None
    selected_offer_version: int | None = None
    delivery_option_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    selection_reason: str
    satisfied_constraints: tuple[str, ...] = ()
    disclosed_compromises: tuple[str, ...] = ()
    rejected_offers: tuple[RejectedOffer, ...] = ()


class StartPurchaseRequest(OrchestrationModel):
    user_id: str
    agent_id: str
    raw_request: str = Field(min_length=3)
    mandate_id: str | None = None
    payment_scenario: PaymentScenario = PaymentScenario.APPROVE
    idempotency_key: str


class ApproveTransactionRequest(OrchestrationModel):
    transaction_id: str
    user_id: str
    approved_content_hash: str
    mandate_id: str | None = None
    idempotency_key: str


class CancelTransactionRequest(OrchestrationModel):
    transaction_id: str
    reason: str = Field(default="User requested cancellation", min_length=1)
    idempotency_key: str


class ReturnTransactionRequest(OrchestrationModel):
    transaction_id: str
    items: dict[str, int] = Field(min_length=1)
    reason: str = Field(min_length=3)
    idempotency_key: str


class TransitionRecord(OrchestrationModel):
    from_state: TransactionState | None
    to_state: TransactionState
    occurred_at: datetime
    reason: str


class AgentTransaction(OrchestrationModel):
    transaction_id: str
    user_id: str
    agent_id: str
    raw_request: str
    mandate_id: str | None
    payment_scenario: PaymentScenario
    state: TransactionState
    intent: NormalizedPurchaseIntent | None = None
    selection: OfferSelectionPlan | None = None
    selected_offer: Offer | None = None
    checkout: Checkout | None = None
    proposal: CheckoutProposal | None = None
    approval_id: str | None = None
    credential_id: str | None = None
    payment_id: str | None = None
    order_id: str | None = None
    return_id: str | None = None
    seen_event_ids: frozenset[str] = Field(default_factory=frozenset)
    last_error_code: str | None = None
    last_error_message: str | None = None
    transitions: tuple[TransitionRecord, ...]
    created_at: datetime
    updated_at: datetime
