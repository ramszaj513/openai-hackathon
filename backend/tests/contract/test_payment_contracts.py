import pytest
from agent_commerce.orchestration.models import ApproveTransactionRequest
from agent_commerce.payments.models import AuthorizePaymentRequest, RefundStatus
from pydantic import ValidationError


def test_refund_status_contract_covers_provider_progression() -> None:
    assert tuple(RefundStatus) == (
        RefundStatus.PENDING,
        RefundStatus.COMPLETED,
        RefundStatus.FAILED,
    )


def test_browser_payment_contract_accepts_only_safe_payment_method_ids() -> None:
    authorization = AuthorizePaymentRequest(
        credential_id="credential_1",
        approval_id="approval_1",
        payment_method_id="pm_browser_card",
        idempotency_key="authorize_1",
    )
    approval = ApproveTransactionRequest(
        transaction_id="transaction_1",
        user_id="user_1",
        approved_content_hash="hash_1",
        payment_method_id=authorization.payment_method_id,
        idempotency_key="approve_1",
    )
    assert approval.payment_method_id == "pm_browser_card"

    with pytest.raises(ValidationError):
        AuthorizePaymentRequest(
            credential_id="credential_1",
            approval_id="approval_1",
            payment_method_id="4242424242424242",
            idempotency_key="authorize_2",
        )
