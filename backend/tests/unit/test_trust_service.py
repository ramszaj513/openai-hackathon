from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from agent_commerce.api import create_app
from agent_commerce.commerce.errors import CommerceError
from agent_commerce.commerce.models import (
    CreateCheckoutRequest,
    OfferSelection,
    UpdateCheckoutRequest,
)
from agent_commerce.commerce.service import CommerceService
from agent_commerce.trust.models import (
    ApprovalStatus,
    CreateCheckoutProposalRequest,
    CreateSpendingMandateRequest,
    EvaluateProposalRequest,
    ExplicitApprovalRequest,
    PolicyOutcome,
)
from agent_commerce.trust.service import TrustService


def create_checkout(commerce: CommerceService) -> object:
    offer = commerce.get_offer("offer-studio-27-usbc")
    return commerce.create_checkout(
        CreateCheckoutRequest(
            transaction_id="txn-trust",
            selections=(
                OfferSelection(
                    offer_id=offer.offer_id,
                    offer_version=offer.version,
                    quantity=1,
                ),
            ),
            delivery_option_id="delivery-next-day",
            idempotency_key="checkout-trust",
        )
    )


def create_proposal(trust: TrustService, commerce: CommerceService) -> tuple[object, object]:
    checkout = create_checkout(commerce)
    proposal = trust.create_proposal(
        checkout,
        CreateCheckoutProposalRequest(
            checkout_id=checkout.checkout_id,
            user_id="user-1",
            agent_id="agent-1",
            selection_reason="Best eligible next-day monitor.",
            satisfied_constraints=("budget", "Mac compatible", "delivery", "returns"),
            idempotency_key="proposal-1",
        ),
    )
    return checkout, proposal


def test_explicit_approval_binds_exact_proposal_hash(
    service: CommerceService, trust: TrustService
) -> None:
    checkout, proposal = create_proposal(trust, service)

    approval = trust.approve_proposal(
        ExplicitApprovalRequest(
            proposal_id=proposal.proposal_id,
            user_id="user-1",
            approved_content_hash=proposal.content_hash,
            idempotency_key="approve-1",
        )
    )
    evidence = trust.get_approval_evidence(approval.approval_id)

    assert evidence.checkout_id == checkout.checkout_id
    assert evidence.checkout_version == checkout.version
    assert evidence.amount_minor == checkout.price.total_minor


def test_wrong_proposal_hash_cannot_be_approved(
    service: CommerceService, trust: TrustService
) -> None:
    _, proposal = create_proposal(trust, service)

    with pytest.raises(CommerceError) as raised:
        trust.approve_proposal(
            ExplicitApprovalRequest(
                proposal_id=proposal.proposal_id,
                user_id="user-1",
                approved_content_hash="tampered",
                idempotency_key="approve-tampered",
            )
        )

    assert raised.value.code == "APPROVAL_INVALID"


def test_mandate_auto_approves_and_reserves_cumulative_budget(
    service: CommerceService,
    trust: TrustService,
    now: datetime,
) -> None:
    _, proposal = create_proposal(trust, service)
    mandate = trust.create_mandate(
        CreateSpendingMandateRequest(
            user_id="user-1",
            agent_id="agent-1",
            allowed_merchant_ids=frozenset({proposal.merchant_id}),
            allowed_categories=frozenset({"monitor"}),
            max_transaction_minor=120000,
            max_total_minor=240000,
            currency="PLN",
            minimum_return_window_days=30,
            latest_delivery_date=proposal.delivery_option.estimated_delivery_date,
            valid_from=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=1),
            idempotency_key="mandate-1",
        )
    )

    decision = trust.evaluate_proposal(
        EvaluateProposalRequest(
            proposal_id=proposal.proposal_id,
            user_id="user-1",
            agent_id="agent-1",
            mandate_id=mandate.mandate_id,
            idempotency_key="evaluate-1",
        )
    )

    assert decision.outcome is PolicyOutcome.AUTO_APPROVED
    assert decision.approval is not None
    updated = trust.get_mandate(mandate.mandate_id)
    assert updated.reserved_amount_minor == proposal.price.total_minor


def test_mandate_denies_purchase_above_limit(
    service: CommerceService,
    trust: TrustService,
    now: datetime,
) -> None:
    _, proposal = create_proposal(trust, service)
    mandate = trust.create_mandate(
        CreateSpendingMandateRequest(
            user_id="user-1",
            agent_id="agent-1",
            max_transaction_minor=100000,
            max_total_minor=100000,
            currency="PLN",
            valid_from=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=1),
            idempotency_key="small-mandate",
        )
    )

    decision = trust.evaluate_proposal(
        EvaluateProposalRequest(
            proposal_id=proposal.proposal_id,
            user_id="user-1",
            agent_id="agent-1",
            mandate_id=mandate.mandate_id,
            idempotency_key="evaluate-denied",
        )
    )

    assert decision.outcome is PolicyOutcome.DENIED
    assert any("per-transaction" in reason for reason in decision.reasons)


def test_checkout_version_change_invalidates_approval(
    service: CommerceService, trust: TrustService
) -> None:
    checkout, proposal = create_proposal(trust, service)
    approval = trust.approve_proposal(
        ExplicitApprovalRequest(
            proposal_id=proposal.proposal_id,
            user_id="user-1",
            approved_content_hash=proposal.content_hash,
            idempotency_key="approve-versioned",
        )
    )
    create_app(service, trust)
    service.update_checkout(
        UpdateCheckoutRequest(
            checkout_id=checkout.checkout_id,
            expected_version=checkout.version,
            delivery_option_id="delivery-standard",
            idempotency_key="change-checkout",
        )
    )

    assert trust.get_approval(approval.approval_id).status is ApprovalStatus.INVALIDATED
    with pytest.raises(CommerceError):
        trust.get_approval_evidence(approval.approval_id)
