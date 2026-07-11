from __future__ import annotations

from datetime import datetime

from agent_commerce.api import create_app
from agent_commerce.commerce.models import SearchOffersRequest
from agent_commerce.commerce.service import CommerceService
from agent_commerce.orchestration.brain import (
    DeterministicOfferPlanner,
    RuleBasedIntentInterpreter,
)
from agent_commerce.orchestration.merchant_gateway import DirectMerchantGateway
from agent_commerce.orchestration.service import CommerceOrchestrator
from agent_commerce.payments.service import PaymentService
from agent_commerce.trust.service import TrustService
from fastapi.testclient import TestClient
from mcp.types import LATEST_PROTOCOL_VERSION


def test_health_and_offer_search_share_commerce_service(service: CommerceService) -> None:
    app = create_app(service)
    request = SearchOffersRequest(
        category="monitor",
        max_unit_price_minor=120000,
        required_attributes={"mac_compatible": True},
        minimum_return_window_days=30,
    )

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.post("/api/offers/search", json=request.model_dump(mode="json"))

    assert response.status_code == 200
    assert {item["offer_id"] for item in response.json()} == {
        "offer-value-24-usbc",
        "offer-studio-27-usbc",
    }


def test_api_returns_stable_commerce_error(service: CommerceService) -> None:
    app = create_app(service)

    with TestClient(app) as client:
        response = client.get("/api/offers/not-real")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_streamable_http_mcp_transport_initializes(service: CommerceService) -> None:
    app = create_app(service)
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": LATEST_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "commerce-contract-test", "version": "1"},
        },
    }

    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        response = client.post(
            "/mcp",
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json=request,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["protocolVersion"] == LATEST_PROTOCOL_VERSION
    assert payload["result"]["capabilities"]["tools"] == {"listChanged": False}


def test_trust_and_payment_api_complete_authorized_purchase(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
) -> None:
    app = create_app(service, trust, payments)
    offer = service.get_offer("offer-studio-27-usbc")

    with TestClient(app) as client:
        checkout_response = client.post(
            "/api/checkouts",
            json={
                "transaction_id": "txn-api-payment",
                "selections": [
                    {
                        "offer_id": offer.offer_id,
                        "offer_version": offer.version,
                        "quantity": 1,
                    }
                ],
                "delivery_option_id": "delivery-next-day",
                "idempotency_key": "api-checkout",
            },
        )
        assert checkout_response.status_code == 201
        checkout = checkout_response.json()

        proposal_response = client.post(
            "/api/trust/proposals",
            json={
                "checkout_id": checkout["checkout_id"],
                "user_id": "user-api",
                "agent_id": "agent-api",
                "selection_reason": "Best eligible offer.",
                "idempotency_key": "api-proposal",
            },
        )
        assert proposal_response.status_code == 201
        proposal = proposal_response.json()

        approval_response = client.post(
            f"/api/trust/proposals/{proposal['proposal_id']}/approve",
            json={
                "proposal_id": proposal["proposal_id"],
                "user_id": "user-api",
                "approved_content_hash": proposal["content_hash"],
                "idempotency_key": "api-approval",
            },
        )
        assert approval_response.status_code == 200
        approval = approval_response.json()

        credential_response = client.post(
            "/api/payments/credentials",
            json={
                "approval_id": approval["approval_id"],
                "user_id": "user-api",
                "idempotency_key": "api-credential",
            },
        )
        assert credential_response.status_code == 201
        credential = credential_response.json()

        authorization_response = client.post(
            "/api/payments/authorize",
            json={
                "credential_id": credential["credential_id"],
                "approval_id": approval["approval_id"],
                "idempotency_key": "api-authorization",
            },
        )
        assert authorization_response.status_code == 200
        authorization = authorization_response.json()

        evidence = client.get(f"/api/trust/approvals/{approval['approval_id']}/evidence").json()
        order_response = client.post(
            f"/api/checkouts/{checkout['checkout_id']}/complete",
            json={
                "checkout_id": checkout["checkout_id"],
                "expected_version": checkout["version"],
                "approval": evidence,
                "payment_authorization": authorization["merchant_reference"],
                "idempotency_key": "api-complete",
            },
        )
        assert order_response.status_code == 200
        order = order_response.json()

        capture_response = client.post(
            f"/api/payments/{authorization['payment']['payment_id']}/capture",
            json={
                "payment_id": authorization["payment"]["payment_id"],
                "order_id": order["order_id"],
                "idempotency_key": "api-capture",
            },
        )

    assert capture_response.status_code == 200
    assert capture_response.json()["status"] == "CAPTURED"


def test_agent_api_runs_to_approval_and_executes_after_consent(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    now: datetime,
) -> None:
    gateway = DirectMerchantGateway(service)
    orchestrator = CommerceOrchestrator(
        merchant=gateway,
        trust=trust,
        payments=payments,
        intent_interpreter=RuleBasedIntentInterpreter(today=now.date()),
        offer_planner=DeterministicOfferPlanner(gateway),
    )
    app = create_app(service, trust, payments, orchestrator)
    with TestClient(app) as client:
        start_response = client.post(
            "/api/agent/transactions",
            json={
                "user_id": "user-agent-api",
                "agent_id": "agent-api",
                "raw_request": (
                    "Buy a Mac-compatible monitor for no more than 1,200 PLN, deliverable "
                    "tomorrow, with a 30-day return. Buy it if confident."
                ),
                "idempotency_key": "agent-api-start",
            },
        )
        assert start_response.status_code == 201
        pending = start_response.json()
        assert pending["state"] == "APPROVAL_PENDING"
        approve_response = client.post(
            f"/api/agent/transactions/{pending['transaction_id']}/approve",
            json={
                "transaction_id": pending["transaction_id"],
                "user_id": "user-agent-api",
                "approved_content_hash": pending["proposal"]["content_hash"],
                "idempotency_key": "agent-api-approve",
            },
        )

    assert approve_response.status_code == 200
    assert approve_response.json()["state"] == "FULFILLING"
