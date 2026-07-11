from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from agent_commerce.commerce.errors import CommerceError
from agent_commerce.commerce.models import (
    CompleteCheckoutRequest,
    CreateCheckoutRequest,
    OfferSelection,
)
from agent_commerce.commerce.service import CommerceService
from agent_commerce.payments.models import (
    AuthorizePaymentRequest,
    CapturePaymentRequest,
    IssuePaymentCredentialRequest,
    PaymentScenario,
    PaymentStatus,
    RecoverAuthorizationRequest,
    RefundPaymentRequest,
)
from agent_commerce.payments.service import PaymentService
from agent_commerce.trust.models import (
    CreateCheckoutProposalRequest,
    CreateSpendingMandateRequest,
    EvaluateProposalRequest,
)
from agent_commerce.trust.service import TrustService


def approved_checkout(
    commerce: CommerceService,
    trust: TrustService,
    now: datetime,
) -> tuple[object, object, object]:
    offer = commerce.get_offer("offer-studio-27-usbc")
    checkout = commerce.create_checkout(
        CreateCheckoutRequest(
            transaction_id="txn-payment",
            selections=(
                OfferSelection(
                    offer_id=offer.offer_id,
                    offer_version=offer.version,
                    quantity=1,
                ),
            ),
            delivery_option_id="delivery-next-day",
            idempotency_key="checkout-payment",
        )
    )
    proposal = trust.create_proposal(
        checkout,
        CreateCheckoutProposalRequest(
            checkout_id=checkout.checkout_id,
            user_id="user-1",
            agent_id="agent-1",
            selection_reason="Best eligible offer.",
            idempotency_key="proposal-payment",
        ),
    )
    mandate = trust.create_mandate(
        CreateSpendingMandateRequest(
            user_id="user-1",
            agent_id="agent-1",
            allowed_merchant_ids=frozenset({checkout.merchant_id}),
            allowed_categories=frozenset({"monitor"}),
            max_transaction_minor=120000,
            max_total_minor=240000,
            currency="PLN",
            minimum_return_window_days=30,
            valid_from=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=1),
            idempotency_key="mandate-payment",
        )
    )
    decision = trust.evaluate_proposal(
        EvaluateProposalRequest(
            proposal_id=proposal.proposal_id,
            user_id="user-1",
            agent_id="agent-1",
            mandate_id=mandate.mandate_id,
            idempotency_key="evaluate-payment",
        )
    )
    assert decision.approval is not None
    return checkout, decision.approval, mandate


def authorize_approved_checkout(payments: PaymentService, approval_id: str) -> object:
    credential = payments.issue_credential(
        IssuePaymentCredentialRequest(
            approval_id=approval_id,
            user_id="user-1",
            idempotency_key="credential-1",
        )
    )
    return payments.authorize(
        AuthorizePaymentRequest(
            credential_id=credential.credential_id,
            approval_id=approval_id,
            idempotency_key="authorize-1",
        )
    )


def test_authorization_is_scoped_to_approved_checkout(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    now: datetime,
) -> None:
    checkout, approval, _ = approved_checkout(service, trust, now)

    result = authorize_approved_checkout(payments, approval.approval_id)

    assert result.payment.status is PaymentStatus.AUTHORIZED
    assert result.merchant_reference is not None
    assert result.merchant_reference.checkout_id == checkout.checkout_id
    assert result.merchant_reference.amount_minor == checkout.price.total_minor


def test_declined_payment_has_no_merchant_authorization(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    now: datetime,
) -> None:
    _, approval, _ = approved_checkout(service, trust, now)
    credential = payments.issue_credential(
        IssuePaymentCredentialRequest(
            approval_id=approval.approval_id,
            user_id="user-1",
            idempotency_key="credential-decline",
        )
    )

    result = payments.authorize(
        AuthorizePaymentRequest(
            credential_id=credential.credential_id,
            approval_id=approval.approval_id,
            scenario=PaymentScenario.DECLINE,
            idempotency_key="authorize-decline",
        )
    )

    assert result.payment.status is PaymentStatus.DECLINED
    assert result.merchant_reference is None


def test_complete_capture_and_refund_update_mandate_spend(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    now: datetime,
) -> None:
    checkout, approval, mandate = approved_checkout(service, trust, now)
    authorization = authorize_approved_checkout(payments, approval.approval_id)
    evidence = trust.get_approval_evidence(approval.approval_id)
    assert authorization.merchant_reference is not None
    order = service.complete_checkout(
        CompleteCheckoutRequest(
            checkout_id=checkout.checkout_id,
            expected_version=checkout.version,
            approval=evidence,
            payment_authorization=authorization.merchant_reference,
            idempotency_key="complete-payment",
        )
    )

    receipt = payments.capture(
        CapturePaymentRequest(
            payment_id=authorization.payment.payment_id,
            order_id=order.order_id,
            idempotency_key="capture-1",
        )
    )

    assert receipt.status is PaymentStatus.CAPTURED
    assert trust.get_mandate(mandate.mandate_id).used_amount_minor == checkout.price.total_minor
    refund = payments.refund(
        RefundPaymentRequest(
            payment_id=receipt.payment_id,
            order_id=order.order_id,
            amount_minor=checkout.price.total_minor,
            reason="Order cancelled",
            idempotency_key="refund-1",
        )
    )
    assert refund.amount_minor == checkout.price.total_minor
    assert trust.get_mandate(mandate.mandate_id).used_amount_minor == 0


def test_orphan_authorization_is_voided_and_approval_invalidated(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    now: datetime,
) -> None:
    _, approval, mandate = approved_checkout(service, trust, now)
    authorization = authorize_approved_checkout(payments, approval.approval_id)

    recovery = payments.recover_authorization(
        RecoverAuthorizationRequest(
            payment_id=authorization.payment.payment_id,
            reconciled_order_id=None,
            idempotency_key="recover-orphan",
        )
    )

    assert recovery.action == "VOIDED_ORPHAN_AUTHORIZATION"
    assert recovery.payment.status is PaymentStatus.VOIDED
    assert trust.get_mandate(mandate.mandate_id).reserved_amount_minor == 0
    with pytest.raises(CommerceError):
        trust.get_approval_evidence(approval.approval_id)


def test_recovery_captures_when_merchant_order_exists(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    now: datetime,
) -> None:
    checkout, approval, mandate = approved_checkout(service, trust, now)
    authorization = authorize_approved_checkout(payments, approval.approval_id)
    assert authorization.merchant_reference is not None
    order = service.complete_checkout(
        CompleteCheckoutRequest(
            checkout_id=checkout.checkout_id,
            expected_version=checkout.version,
            approval=trust.get_approval_evidence(approval.approval_id),
            payment_authorization=authorization.merchant_reference,
            idempotency_key="complete-before-recovery",
        )
    )

    recovery = payments.recover_authorization(
        RecoverAuthorizationRequest(
            payment_id=authorization.payment.payment_id,
            reconciled_order_id=order.order_id,
            idempotency_key="recover-existing-order",
        )
    )

    assert recovery.action == "CAPTURED_EXISTING_ORDER"
    assert recovery.payment.status is PaymentStatus.CAPTURED
    assert trust.get_mandate(mandate.mandate_id).used_amount_minor == checkout.price.total_minor


def test_authorization_idempotency_prevents_duplicate_charge(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    now: datetime,
) -> None:
    _, approval, _ = approved_checkout(service, trust, now)
    credential = payments.issue_credential(
        IssuePaymentCredentialRequest(
            approval_id=approval.approval_id,
            user_id="user-1",
            idempotency_key="credential-idempotent",
        )
    )
    request = AuthorizePaymentRequest(
        credential_id=credential.credential_id,
        approval_id=approval.approval_id,
        idempotency_key="authorize-idempotent",
    )

    first = payments.authorize(request)
    second = payments.authorize(request)

    assert first == second
    with pytest.raises(CommerceError):
        payments.authorize(
            request.model_copy(update={"idempotency_key": "different-authorization"})
        )
