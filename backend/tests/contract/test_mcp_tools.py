from __future__ import annotations

from datetime import datetime

import pytest
from agent_commerce.commerce.models import SearchOffersRequest
from agent_commerce.commerce.service import CommerceService
from agent_commerce.mcp_server import create_commerce_mcp


@pytest.mark.asyncio
async def test_mcp_exposes_canonical_commerce_tools(service: CommerceService) -> None:
    server = create_commerce_mcp(service)

    names = {tool.name for tool in await server.list_tools()}

    assert {
        "search_offers",
        "get_offer",
        "get_delivery_options",
        "get_return_policy",
        "create_checkout",
        "get_checkout",
        "update_checkout",
        "cancel_checkout",
        "complete_checkout",
        "get_order",
        "get_order_by_checkout",
        "cancel_order",
        "create_return",
        "list_transaction_events",
    } <= names


@pytest.mark.asyncio
async def test_mcp_search_returns_structured_result(
    service: CommerceService, now: datetime
) -> None:
    server = create_commerce_mcp(service)
    request = SearchOffersRequest(
        category="monitor",
        max_unit_price_minor=120000,
        required_attributes={"mac_compatible": True},
        latest_delivery_date=now.date().replace(day=12),
        minimum_return_window_days=30,
    )

    _, structured = await server.call_tool(
        "search_offers", {"request": request.model_dump(mode="json")}
    )

    assert structured["ok"] is True
    assert structured["data"]["result"][0]["offer_id"] == "offer-studio-27-usbc"
