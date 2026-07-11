from __future__ import annotations

import socket
import threading
import time
from datetime import datetime

import pytest
import uvicorn
from agent_commerce.api import create_app
from agent_commerce.commerce.models import (
    CreateCheckoutRequest,
    OfferSelection,
    SearchOffersRequest,
)
from agent_commerce.commerce.service import CommerceService
from agent_commerce.orchestration.merchant_gateway import MCPMerchantGateway
from agent_commerce.payments.service import PaymentService
from agent_commerce.trust.service import TrustService
from agents.mcp import MCPServerStreamableHttp, create_static_tool_filter


def _available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_agent_gateway_uses_real_streamable_http_mcp(
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
    now: datetime,
) -> None:
    port = _available_port()
    app = create_app(service, trust, payments)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started
    gateway = MCPMerchantGateway(f"http://127.0.0.1:{port}/mcp")
    try:
        offers = await gateway.search_offers(
            SearchOffersRequest(
                category="monitor",
                max_unit_price_minor=120000,
                required_attributes={"mac_compatible": True},
                latest_delivery_date=now.date().replace(day=12),
                minimum_return_window_days=30,
            )
        )
        assert [offer.offer_id for offer in offers] == ["offer-studio-27-usbc"]
        checkout = await gateway.create_checkout(
            CreateCheckoutRequest(
                transaction_id="txn-real-mcp",
                selections=(
                    OfferSelection(
                        offer_id=offers[0].offer_id,
                        offer_version=offers[0].version,
                        quantity=1,
                    ),
                ),
                delivery_option_id="delivery-next-day",
                idempotency_key="real-mcp-checkout",
            )
        )
        assert checkout.transaction_id == "txn-real-mcp"
        agent_mcp = MCPServerStreamableHttp(
            params={"url": f"http://127.0.0.1:{port}/mcp"},
            tool_filter=create_static_tool_filter(
                allowed_tool_names=["search_offers", "get_offer"]
            ),
            use_structured_content=True,
        )
        async with agent_mcp:
            tool_names = {tool.name for tool in await agent_mcp.list_tools()}
        assert tool_names == {"search_offers", "get_offer"}
    finally:
        server.should_exit = True
        thread.join(timeout=5)
