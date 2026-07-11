from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
from agent_commerce.commerce.errors import CommerceError
from agent_commerce.payments.models import (
    CredentialStatus,
    PaymentCredential,
    PaymentScenario,
    PaymentStatus,
    RefundStatus,
)
from agent_commerce.payments.repository import InMemoryPaymentRepository
from agent_commerce.payments.settings import PaymentProvider, PaymentSettings
from agent_commerce.payments.stripe_adapter import StripePaymentAdapter
from pydantic import ValidationError

NOW = datetime(2026, 7, 11, 10, 0, tzinfo=UTC)


def credential() -> PaymentCredential:
    return PaymentCredential(
        credential_id="credential_1",
        approval_id="approval_1",
        transaction_id="transaction_1",
        user_id="user_1",
        merchant_id="merchant_1",
        checkout_id="checkout_1",
        checkout_version=1,
        max_amount_minor=119900,
        currency="PLN",
        status=CredentialStatus.ISSUED,
        expires_at=NOW + timedelta(minutes=10),
        created_at=NOW,
        updated_at=NOW,
    )


def make_adapter(
    handler: httpx.MockTransport,
) -> tuple[StripePaymentAdapter, InMemoryPaymentRepository]:
    repository = InMemoryPaymentRepository()
    client = httpx.Client(transport=handler)
    return (
        StripePaymentAdapter(
            repository,
            clock=lambda: NOW,
            secret_key="sk_test_unit",
            client=client,
        ),
        repository,
    )


def form(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(request.content.decode())


def test_stripe_card_authorize_capture_and_refund_lifecycle() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        data = form(request)
        if request.url.path == "/v1/payment_intents":
            assert data["capture_method"] == ["manual"]
            assert data["confirm"] == ["true"]
            assert data["amount"] == ["119900"]
            assert data["currency"] == ["pln"]
            assert "client_secret" not in data
            return httpx.Response(
                200,
                json={
                    "id": "pi_test_1",
                    "status": "requires_capture",
                    "amount": 119900,
                    "currency": "pln",
                },
            )
        if request.url.path == "/v1/payment_intents/pi_test_1/capture":
            assert data["metadata[order_id]"] == ["order_1"]
            return httpx.Response(
                200,
                json={
                    "id": "pi_test_1",
                    "status": "succeeded",
                    "amount_received": 119900,
                    "currency": "pln",
                },
            )
        if request.url.path == "/v1/refunds":
            assert data["payment_intent"] == ["pi_test_1"]
            assert data["amount"] == ["119900"]
            return httpx.Response(
                200,
                json={
                    "id": "re_test_1",
                    "status": "succeeded",
                    "amount": 119900,
                    "currency": "pln",
                },
            )
        raise AssertionError(f"Unexpected Stripe path: {request.url.path}")

    adapter, repository = make_adapter(httpx.MockTransport(handler))
    authorized = adapter.authorize(
        credential(),
        scenario=PaymentScenario.APPROVE,
        payment_id="pay_1",
        idempotency_key="authorize_1",
    )
    captured = adapter.capture(
        authorized.payment_id,
        "order_1",
        119900,
        idempotency_key="capture_1",
    )
    updated, refund = adapter.refund(
        captured.payment_id,
        "order_1",
        119900,
        "Customer cancellation",
        "refund_1",
        idempotency_key="refund_1",
    )

    assert authorized.status is PaymentStatus.AUTHORIZED
    assert authorized.provider_reference == "pi_test_1"
    assert captured.status is PaymentStatus.CAPTURED
    assert updated.status is PaymentStatus.REFUNDED
    assert refund.status is RefundStatus.COMPLETED
    assert refund.provider_reference == "re_test_1"
    assert repository.get_payment("pay_1") == updated
    assert [request.headers["Idempotency-Key"] for request in requests] == [
        stripe_key("authorize", "authorize_1"),
        stripe_key("capture", "capture_1"),
        stripe_key("refund", "refund_1"),
    ]


def test_stripe_decline_is_safe_and_has_no_authorized_amount() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert form(request)["payment_method"] == ["pm_card_visa_chargeDeclined"]
        return httpx.Response(
            402,
            json={
                "error": {
                    "type": "card_error",
                    "code": "card_declined",
                    "decline_code": "generic_decline",
                    "message": "Sensitive provider text is not propagated",
                    "payment_intent": {"id": "pi_declined_1", "client_secret": "secret"},
                }
            },
        )

    adapter, _ = make_adapter(httpx.MockTransport(handler))
    payment = adapter.authorize(
        credential(),
        scenario=PaymentScenario.DECLINE,
        payment_id="pay_declined",
        idempotency_key="decline_1",
    )

    assert payment.status is PaymentStatus.DECLINED
    assert payment.authorized_amount_minor == 0
    assert payment.provider_reference == "pi_declined_1"
    assert "secret" not in payment.model_dump_json()


def test_stripe_authorization_can_be_voided() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/payment_intents":
            return httpx.Response(
                200,
                json={
                    "id": "pi_void_1",
                    "status": "requires_capture",
                    "amount": 119900,
                    "currency": "pln",
                },
            )
        assert request.url.path == "/v1/payment_intents/pi_void_1/cancel"
        assert form(request)["cancellation_reason"] == ["abandoned"]
        return httpx.Response(200, json={"id": "pi_void_1", "status": "canceled"})

    adapter, _ = make_adapter(httpx.MockTransport(handler))
    authorized = adapter.authorize(
        credential(),
        scenario=PaymentScenario.APPROVE,
        payment_id="pay_void",
        idempotency_key="authorize_void",
    )

    voided = adapter.void(authorized.payment_id, idempotency_key="void_1")

    assert voided.status is PaymentStatus.VOIDED


def test_stripe_transport_failure_requires_same_key_retry() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("unknown outcome")

    adapter, repository = make_adapter(httpx.MockTransport(handler))

    with pytest.raises(CommerceError) as raised:
        adapter.authorize(
            credential(),
            scenario=PaymentScenario.APPROVE,
            payment_id="pay_timeout",
            idempotency_key="authorize_timeout",
        )

    assert raised.value.code == "TEMPORARILY_UNAVAILABLE"
    assert repository.get_payment("pay_timeout") is None


def test_stripe_settings_require_a_test_mode_key() -> None:
    with pytest.raises(ValidationError, match="STRIPE_SECRET_KEY"):
        PaymentSettings(payment_provider=PaymentProvider.STRIPE)
    with pytest.raises(ValidationError, match="test-mode"):
        PaymentSettings(
            payment_provider=PaymentProvider.STRIPE,
            stripe_secret_key="sk_live_forbidden",
        )

    settings = PaymentSettings(
        payment_provider=PaymentProvider.STRIPE,
        stripe_secret_key="sk_test_configured",
    )
    assert settings.payment_provider is PaymentProvider.STRIPE
    assert "sk_test_configured" not in repr(settings)


def stripe_key(operation: str, application_key: str) -> str:
    digest = hashlib.sha256(application_key.encode()).hexdigest()
    return f"acg:{operation}:{digest}"
