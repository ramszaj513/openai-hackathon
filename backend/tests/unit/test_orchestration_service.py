from __future__ import annotations

from datetime import datetime, timedelta
from itertools import count

import pytest
from agent_commerce.audit import AuditLedger
from agent_commerce.commerce.models import (
    CompleteCheckoutRequest,
    OrderState,
    SetOrderStateRequest,
)
from agent_commerce.commerce.service import CommerceService
from agent_commerce.orchestration.brain import DeterministicOfferPlanner
from agent_commerce.orchestration.merchant_gateway import (
    AmbiguousMerchantError,
    DirectMerchantGateway,
)
from agent_commerce.orchestration.models import (
    ApproveTransactionRequest,
    CancelTransactionRequest,
    NormalizedPurchaseIntent,
    ReturnTransactionRequest,
    StartPurchaseRequest,
    TransactionState,
)
from agent_commerce.orchestration.repository import InMemoryTransactionRepository
from agent_commerce.orchestration.service import CommerceOrchestrator
from agent_commerce.payments.models import PaymentScenario, PaymentStatus
from agent_commerce.payments.service import PaymentService
from agent_commerce.trust.models import CreateSpendingMandateRequest
from agent_commerce.trust.service import TrustService
from conftest import MutableClock, StaticIntentInterpreter, canonical_intent

CANONICAL_REQUEST = (
    "Buy a Mac-compatible monitor for no more than 1,200 PLN, deliverable tomorrow, "
    "with at least a 30-day return window. Buy it if you are confident."
)


def build_orchestrator(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    audit: AuditLedger,
    clock: MutableClock,
    now: datetime,
    gateway: DirectMerchantGateway | None = None,
    intent: NormalizedPurchaseIntent | None = None,
) -> CommerceOrchestrator:
    merchant = gateway or DirectMerchantGateway(service)
    ids = count(1)
    return CommerceOrchestrator(
        merchant=merchant,
        trust=trust,
        payments=payments,
        intent_interpreter=StaticIntentInterpreter(intent or canonical_intent(now)),
        offer_planner=DeterministicOfferPlanner(merchant),
        repository=InMemoryTransactionRepository(),
        audit=audit,
        clock=clock,
        id_factory=lambda: f"{next(ids):08d}",
    )


def create_mandate(trust: TrustService, now: datetime) -> str:
    mandate = trust.create_mandate(
        CreateSpendingMandateRequest(
            user_id="user-1",
            agent_id="agent-1",
            allowed_merchant_ids=frozenset({"merchant-demo-electronics"}),
            allowed_categories=frozenset({"monitor"}),
            max_transaction_minor=120000,
            max_total_minor=240000,
            currency="PLN",
            minimum_return_window_days=30,
            latest_delivery_date=now.date() + timedelta(days=1),
            valid_from=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=1),
            idempotency_key="orchestration-mandate",
        )
    )
    return mandate.mandate_id


@pytest.mark.asyncio
async def test_missing_budget_requires_clarification_without_checkout(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    audit: AuditLedger,
    clock: MutableClock,
    now: datetime,
) -> None:
    orchestrator = build_orchestrator(
        service,
        trust,
        payments,
        audit,
        clock,
        now,
        intent=canonical_intent(
            now,
            max_budget_minor=None,
            missing_required_fields=("max_budget_minor",),
        ),
    )

    transaction = await orchestrator.start(
        StartPurchaseRequest(
            user_id="user-1",
            agent_id="agent-1",
            raw_request="Find me a Mac-compatible monitor.",
            idempotency_key="clarification-start",
        )
    )

    assert transaction.state is TransactionState.CLARIFICATION_REQUIRED
    assert transaction.intent is not None
    assert "max_budget_minor" in transaction.intent.missing_required_fields
    assert transaction.checkout is None


@pytest.mark.asyncio
async def test_explicit_approval_completes_purchase(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    audit: AuditLedger,
    clock: MutableClock,
    now: datetime,
) -> None:
    orchestrator = build_orchestrator(service, trust, payments, audit, clock, now)
    pending = await orchestrator.start(
        StartPurchaseRequest(
            user_id="user-1",
            agent_id="agent-1",
            raw_request=CANONICAL_REQUEST,
            idempotency_key="explicit-start",
        )
    )
    assert pending.state is TransactionState.APPROVAL_PENDING
    assert pending.proposal is not None

    completed = await orchestrator.approve(
        ApproveTransactionRequest(
            transaction_id=pending.transaction_id,
            user_id="user-1",
            approved_content_hash=pending.proposal.content_hash,
            idempotency_key="explicit-approve",
        )
    )

    assert completed.state is TransactionState.FULFILLING
    assert completed.order_id is not None
    assert completed.payment_id is not None
    assert payments.get_payment(completed.payment_id).status is PaymentStatus.CAPTURED


@pytest.mark.asyncio
async def test_confident_purchase_auto_executes_under_mandate(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    audit: AuditLedger,
    clock: MutableClock,
    now: datetime,
) -> None:
    orchestrator = build_orchestrator(service, trust, payments, audit, clock, now)
    mandate_id = create_mandate(trust, now)

    transaction = await orchestrator.start(
        StartPurchaseRequest(
            user_id="user-1",
            agent_id="agent-1",
            raw_request=CANONICAL_REQUEST,
            mandate_id=mandate_id,
            idempotency_key="auto-start",
        )
    )

    assert transaction.state is TransactionState.FULFILLING
    assert transaction.selection is not None
    assert transaction.selection.selected_offer_id == "offer-studio-27-usbc"


@pytest.mark.asyncio
async def test_agent_does_not_buy_when_no_offer_meets_budget(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    audit: AuditLedger,
    clock: MutableClock,
    now: datetime,
) -> None:
    orchestrator = build_orchestrator(
        service,
        trust,
        payments,
        audit,
        clock,
        now,
        intent=canonical_intent(now, max_budget_minor=50000),
    )

    transaction = await orchestrator.start(
        StartPurchaseRequest(
            user_id="user-1",
            agent_id="agent-1",
            raw_request=(
                "Buy a Mac-compatible monitor for no more than 500 PLN with a 30-day return."
            ),
            idempotency_key="no-offer-start",
        )
    )

    assert transaction.state is TransactionState.NO_MATCH
    assert transaction.selection is not None
    assert transaction.selection.selected_offer_id is None
    assert transaction.selection.confidence == 1
    assert "none satisfies" in transaction.selection.selection_reason
    assert transaction.last_error_code is None


@pytest.mark.asyncio
async def test_agent_confidently_reports_product_absent_from_catalog(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    audit: AuditLedger,
    clock: MutableClock,
    now: datetime,
) -> None:
    intent = NormalizedPurchaseIntent(
        product_query="wireless noise cancelling headphones",
        category="headphones",
        max_budget_minor=100000,
        currency="PLN",
        purchase_if_confident=True,
    )
    orchestrator = build_orchestrator(
        service,
        trust,
        payments,
        audit,
        clock,
        now,
        intent=intent,
    )

    transaction = await orchestrator.start(
        StartPurchaseRequest(
            user_id="user-1",
            agent_id="agent-1",
            raw_request="Any natural-language request is interpreted upstream by the model.",
            idempotency_key="product-not-stocked",
        )
    )

    assert transaction.state is TransactionState.NO_MATCH
    assert transaction.selection is not None
    assert transaction.selection.confidence == 1
    assert "wireless noise cancelling headphones" in transaction.selection.selection_reason


@pytest.mark.asyncio
async def test_payment_decline_never_creates_order(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    audit: AuditLedger,
    clock: MutableClock,
    now: datetime,
) -> None:
    orchestrator = build_orchestrator(service, trust, payments, audit, clock, now)
    pending = await orchestrator.start(
        StartPurchaseRequest(
            user_id="user-1",
            agent_id="agent-1",
            raw_request=CANONICAL_REQUEST,
            payment_scenario=PaymentScenario.DECLINE,
            idempotency_key="decline-start",
        )
    )
    assert pending.proposal is not None

    transaction = await orchestrator.approve(
        ApproveTransactionRequest(
            transaction_id=pending.transaction_id,
            user_id="user-1",
            approved_content_hash=pending.proposal.content_hash,
            idempotency_key="decline-approve",
        )
    )

    assert transaction.state is TransactionState.FAILED
    assert transaction.last_error_code == "PAYMENT_DECLINED"
    assert transaction.order_id is None


class AmbiguousAfterCommitGateway(DirectMerchantGateway):
    async def complete_checkout(self, request: CompleteCheckoutRequest):  # type: ignore[no-untyped-def]
        self.service.complete_checkout(request)
        raise AmbiguousMerchantError("Response lost after merchant commit")


class AmbiguousBeforeCommitGateway(DirectMerchantGateway):
    async def complete_checkout(self, request: CompleteCheckoutRequest):  # type: ignore[no-untyped-def]
        raise AmbiguousMerchantError("Request timed out before merchant commit")


@pytest.mark.asyncio
async def test_ambiguous_completion_finds_existing_order_and_captures_once(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    audit: AuditLedger,
    clock: MutableClock,
    now: datetime,
) -> None:
    gateway = AmbiguousAfterCommitGateway(service)
    orchestrator = build_orchestrator(service, trust, payments, audit, clock, now, gateway)
    mandate_id = create_mandate(trust, now)

    transaction = await orchestrator.start(
        StartPurchaseRequest(
            user_id="user-1",
            agent_id="agent-1",
            raw_request=CANONICAL_REQUEST,
            mandate_id=mandate_id,
            idempotency_key="ambiguous-after",
        )
    )

    assert transaction.state is TransactionState.FULFILLING
    assert transaction.order_id is not None
    assert transaction.payment_id is not None
    assert payments.get_payment(transaction.payment_id).status is PaymentStatus.CAPTURED


@pytest.mark.asyncio
async def test_ambiguous_completion_without_order_voids_authorization(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    audit: AuditLedger,
    clock: MutableClock,
    now: datetime,
) -> None:
    gateway = AmbiguousBeforeCommitGateway(service)
    orchestrator = build_orchestrator(service, trust, payments, audit, clock, now, gateway)
    mandate_id = create_mandate(trust, now)

    transaction = await orchestrator.start(
        StartPurchaseRequest(
            user_id="user-1",
            agent_id="agent-1",
            raw_request=CANONICAL_REQUEST,
            mandate_id=mandate_id,
            idempotency_key="ambiguous-before",
        )
    )

    assert transaction.state is TransactionState.FAILED
    assert transaction.last_error_code == "ORDER_NOT_CREATED"
    assert transaction.payment_id is not None
    assert payments.get_payment(transaction.payment_id).status is PaymentStatus.VOIDED


@pytest.mark.asyncio
async def test_order_events_resume_agent_and_return_flow_refunds(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    audit: AuditLedger,
    clock: MutableClock,
    now: datetime,
) -> None:
    orchestrator = build_orchestrator(service, trust, payments, audit, clock, now)
    mandate_id = create_mandate(trust, now)
    transaction = await orchestrator.start(
        StartPurchaseRequest(
            user_id="user-1",
            agent_id="agent-1",
            raw_request=CANONICAL_REQUEST,
            mandate_id=mandate_id,
            idempotency_key="return-start",
        )
    )
    assert transaction.order_id is not None
    for state in (OrderState.PROCESSING, OrderState.SHIPPED, OrderState.DELIVERED):
        service.set_order_state(
            SetOrderStateRequest(
                order_id=transaction.order_id,
                state=state,
                idempotency_key=f"return-state-{state}",
            )
        )

    delivered = await orchestrator.resume_from_events(transaction.transaction_id)
    assert delivered.state is TransactionState.DELIVERED
    assert delivered.checkout is not None
    refunded = await orchestrator.return_order(
        ReturnTransactionRequest(
            transaction_id=delivered.transaction_id,
            items={delivered.checkout.lines[0].product_id: 1},
            reason="Changed my mind",
            idempotency_key="return-request",
        )
    )

    assert refunded.state is TransactionState.REFUNDED
    assert refunded.return_id is not None


@pytest.mark.asyncio
async def test_cancellation_flow_refunds_captured_payment(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    audit: AuditLedger,
    clock: MutableClock,
    now: datetime,
) -> None:
    orchestrator = build_orchestrator(service, trust, payments, audit, clock, now)
    mandate_id = create_mandate(trust, now)
    transaction = await orchestrator.start(
        StartPurchaseRequest(
            user_id="user-1",
            agent_id="agent-1",
            raw_request=CANONICAL_REQUEST,
            mandate_id=mandate_id,
            idempotency_key="cancel-start",
        )
    )

    refunded = await orchestrator.cancel(
        CancelTransactionRequest(
            transaction_id=transaction.transaction_id,
            idempotency_key="cancel-request",
        )
    )

    assert refunded.state is TransactionState.REFUNDED
    assert refunded.payment_id is not None
    assert payments.get_payment(refunded.payment_id).status is PaymentStatus.REFUNDED
