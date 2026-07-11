from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from agent_commerce.commerce.errors import CommerceError
from agent_commerce.commerce.models import (
    ApprovalEvidence,
    CancelOrderRequest,
    Checkout,
    CompleteCheckoutRequest,
    CreateCheckoutRequest,
    CreateReturnRequest,
    OfferSelection,
    OrderState,
    PaymentAuthorizationReference,
    SearchOffersRequest,
    SetOrderStateRequest,
    UpdateCheckoutRequest,
)
from agent_commerce.commerce.seed import canonical_latest_delivery_date
from agent_commerce.commerce.service import CommerceService
from conftest import MutableClock


def canonical_search(now: datetime) -> SearchOffersRequest:
    return SearchOffersRequest(
        category="monitor",
        max_unit_price_minor=120000,
        required_attributes={"mac_compatible": True},
        latest_delivery_date=canonical_latest_delivery_date(now.date()),
        minimum_return_window_days=30,
    )


def create_canonical_checkout(service: CommerceService) -> Checkout:
    offer = service.get_offer("offer-studio-27-usbc")
    return service.create_checkout(
        CreateCheckoutRequest(
            transaction_id="txn-canonical",
            selections=(
                OfferSelection(
                    offer_id=offer.offer_id,
                    offer_version=offer.version,
                    quantity=1,
                ),
            ),
            delivery_option_id="delivery-next-day",
            idempotency_key="create-canonical",
        )
    )


def valid_authorities(
    checkout: Checkout, now: datetime
) -> tuple[ApprovalEvidence, PaymentAuthorizationReference]:
    approval = ApprovalEvidence(
        approval_id="approval-1",
        checkout_id=checkout.checkout_id,
        checkout_version=checkout.version,
        merchant_id=checkout.merchant_id,
        amount_minor=checkout.price.total_minor,
        currency=checkout.price.currency,
        expires_at=now + timedelta(minutes=10),
    )
    payment = PaymentAuthorizationReference(
        payment_authorization_id="payment-auth-1",
        checkout_id=checkout.checkout_id,
        checkout_version=checkout.version,
        merchant_id=checkout.merchant_id,
        amount_minor=checkout.price.total_minor,
        currency=checkout.price.currency,
        expires_at=now + timedelta(minutes=10),
    )
    return approval, payment


def test_canonical_search_returns_only_eligible_offer(
    service: CommerceService, now: datetime
) -> None:
    offers = service.search_offers(canonical_search(now))

    assert [offer.offer_id for offer in offers] == ["offer-studio-27-usbc"]


def test_checkout_reserves_inventory_and_is_idempotent(service: CommerceService) -> None:
    before = service.get_offer("offer-studio-27-usbc")
    request = CreateCheckoutRequest(
        transaction_id="txn-1",
        selections=(
            OfferSelection(
                offer_id=before.offer_id,
                offer_version=before.version,
                quantity=2,
            ),
        ),
        delivery_option_id="delivery-next-day",
        idempotency_key="create-1",
    )

    first = service.create_checkout(request)
    second = service.create_checkout(request)

    assert second == first
    assert service.get_offer(before.offer_id).available_quantity == before.available_quantity - 2
    assert first.price.total_minor == 2 * before.unit_price.amount_minor


def test_idempotency_key_rejects_a_different_request(service: CommerceService) -> None:
    offer = service.get_offer("offer-studio-27-usbc")
    base = dict(
        transaction_id="txn-1",
        selections=(
            OfferSelection(
                offer_id=offer.offer_id,
                offer_version=offer.version,
                quantity=1,
            ),
        ),
        delivery_option_id="delivery-next-day",
        idempotency_key="same-key",
    )
    service.create_checkout(CreateCheckoutRequest(**base))

    with pytest.raises(CommerceError) as raised:
        service.create_checkout(CreateCheckoutRequest(**{**base, "transaction_id": "txn-2"}))

    assert raised.value.code == "IDEMPOTENCY_CONFLICT"


def test_checkout_expiry_releases_inventory(service: CommerceService, clock: MutableClock) -> None:
    checkout = create_canonical_checkout(service)
    reserved_offer = service.get_offer(checkout.lines[0].offer_id)
    clock.advance(minutes=16)

    expired = service.get_checkout(checkout.checkout_id)

    assert expired.state == "EXPIRED"
    assert service.get_offer(reserved_offer.offer_id).available_quantity == 5


def test_checkout_update_invalidates_old_approval(service: CommerceService, now: datetime) -> None:
    checkout = create_canonical_checkout(service)
    approval, payment = valid_authorities(checkout, now)
    updated = service.update_checkout(
        UpdateCheckoutRequest(
            checkout_id=checkout.checkout_id,
            expected_version=checkout.version,
            delivery_option_id="delivery-standard",
            idempotency_key="update-delivery",
        )
    )

    with pytest.raises(CommerceError) as raised:
        service.complete_checkout(
            CompleteCheckoutRequest(
                checkout_id=updated.checkout_id,
                expected_version=updated.version,
                approval=approval,
                payment_authorization=payment,
                idempotency_key="complete-stale-approval",
            )
        )

    assert raised.value.code == "APPROVAL_INVALID"


def test_complete_checkout_is_idempotent_and_emits_order_event(
    service: CommerceService, now: datetime
) -> None:
    checkout = create_canonical_checkout(service)
    approval, payment = valid_authorities(checkout, now)
    request = CompleteCheckoutRequest(
        checkout_id=checkout.checkout_id,
        expected_version=checkout.version,
        approval=approval,
        payment_authorization=payment,
        idempotency_key="complete-1",
    )

    first = service.complete_checkout(request)
    second = service.complete_checkout(request)

    assert second == first
    assert first.state is OrderState.CONFIRMED
    assert [event.event_type for event in service.list_events(first.transaction_id)][-1] == (
        "order.confirmed"
    )


def test_cancel_order_releases_stock_and_requests_refund(
    service: CommerceService, now: datetime
) -> None:
    checkout = create_canonical_checkout(service)
    approval, payment = valid_authorities(checkout, now)
    order = service.complete_checkout(
        CompleteCheckoutRequest(
            checkout_id=checkout.checkout_id,
            expected_version=checkout.version,
            approval=approval,
            payment_authorization=payment,
            idempotency_key="complete-cancel",
        )
    )

    cancelled = service.cancel_order(
        CancelOrderRequest(order_id=order.order_id, idempotency_key="cancel-order")
    )

    assert cancelled.state is OrderState.CANCELLED
    assert service.get_offer(checkout.lines[0].offer_id).available_quantity == 5
    assert [event.event_type for event in service.list_events(order.transaction_id)][-2:] == [
        "order.cancelled",
        "refund.pending",
    ]


def test_delivered_order_can_create_return(service: CommerceService, now: datetime) -> None:
    checkout = create_canonical_checkout(service)
    approval, payment = valid_authorities(checkout, now)
    order = service.complete_checkout(
        CompleteCheckoutRequest(
            checkout_id=checkout.checkout_id,
            expected_version=checkout.version,
            approval=approval,
            payment_authorization=payment,
            idempotency_key="complete-return",
        )
    )
    for state in (OrderState.PROCESSING, OrderState.SHIPPED, OrderState.DELIVERED):
        order = service.set_order_state(
            SetOrderStateRequest(
                order_id=order.order_id,
                state=state,
                idempotency_key=f"state-{state}",
            )
        )

    record = service.create_return(
        CreateReturnRequest(
            order_id=order.order_id,
            items={order.lines[0].product_id: 1},
            reason="Changed my mind",
            idempotency_key="return-1",
        )
    )

    assert record.state == "AUTHORIZED"
    assert record.refund_amount.amount_minor == order.lines[0].unit_price.amount_minor
