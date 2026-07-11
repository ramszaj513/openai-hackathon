from __future__ import annotations

from fastapi.testclient import TestClient
from mcp.types import LATEST_PROTOCOL_VERSION

from agent_commerce.api import create_app
from agent_commerce.commerce.models import SearchOffersRequest
from agent_commerce.commerce.service import CommerceService


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
        response = client.post(
            "/api/offers/search", json=request.model_dump(mode="json")
        )

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
