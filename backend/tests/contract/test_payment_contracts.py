from agent_commerce.payments.models import RefundStatus


def test_refund_status_contract_covers_provider_progression() -> None:
    assert tuple(RefundStatus) == (
        RefundStatus.PENDING,
        RefundStatus.COMPLETED,
        RefundStatus.FAILED,
    )
