"""FastMCP tools backed by the authoritative commerce application service."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from agent_commerce.commerce.errors import CommerceError
from agent_commerce.commerce.models import (
    CancelCheckoutRequest,
    CancelOrderRequest,
    CompleteCheckoutRequest,
    CreateCheckoutRequest,
    CreateReturnRequest,
    ToolResult,
    UpdateCheckoutRequest,
)
from agent_commerce.commerce.service import CommerceService
from agent_commerce.mcp_server.models import SearchOffersToolRequest

ResultT = TypeVar("ResultT", bound=BaseModel)


def _serialize(
    value: BaseModel | Sequence[BaseModel],
) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(value, Sequence):
        return [item.model_dump(mode="json") for item in value]
    return value.model_dump(mode="json")


def _execute(operation: Callable[[], BaseModel | Sequence[BaseModel]]) -> ToolResult:
    try:
        return ToolResult(ok=True, data={"result": _serialize(operation())})
    except CommerceError as exc:
        return ToolResult(ok=False, error=exc.as_dict())


def create_commerce_mcp(service: CommerceService) -> FastMCP:
    """Create the merchant MCP surface over an injected commerce service."""

    server = FastMCP(
        name="Agent Commerce Merchant",
        instructions=(
            "Use these tools to discover structured merchant offers, create and manage "
            "versioned checkouts, complete approved purchases, and manage orders/returns. "
            "Treat every returned version and expiry as authoritative."
        ),
        stateless_http=True,
        json_response=True,
    )

    @server.tool(name="search_offers")
    def search_offers(request: SearchOffersToolRequest) -> ToolResult:
        """Find current structured offers matching hard purchase constraints."""
        return _execute(lambda: service.search_offers(request.to_domain()))

    @server.tool(name="get_offer")
    def get_offer(offer_id: str) -> ToolResult:
        """Retrieve one current offer including its version, stock, terms, and expiry."""
        return _execute(lambda: service.get_offer(offer_id))

    @server.tool(name="get_delivery_options")
    def get_delivery_options(offer_id: str) -> ToolResult:
        """Retrieve current delivery choices for an offer."""
        return _execute(lambda: list(service.get_offer(offer_id).delivery_options))

    @server.tool(name="get_return_policy")
    def get_return_policy(offer_id: str) -> ToolResult:
        """Retrieve the machine-readable return policy for an offer."""
        return _execute(lambda: service.get_offer(offer_id).return_policy)

    @server.tool(name="create_checkout")
    def create_checkout(request: CreateCheckoutRequest) -> ToolResult:
        """Reserve stock and create a merchant-authoritative versioned checkout."""
        return _execute(lambda: service.create_checkout(request))

    @server.tool(name="get_checkout")
    def get_checkout(checkout_id: str) -> ToolResult:
        """Retrieve authoritative checkout state, expiring it when necessary."""
        return _execute(lambda: service.get_checkout(checkout_id))

    @server.tool(name="update_checkout")
    def update_checkout(request: UpdateCheckoutRequest) -> ToolResult:
        """Change checkout quantities or delivery using optimistic version control."""
        return _execute(lambda: service.update_checkout(request))

    @server.tool(name="cancel_checkout")
    def cancel_checkout(request: CancelCheckoutRequest) -> ToolResult:
        """Cancel a draft checkout and release its inventory reservation."""
        return _execute(lambda: service.cancel_checkout(request))

    @server.tool(name="complete_checkout")
    def complete_checkout(request: CompleteCheckoutRequest) -> ToolResult:
        """Validate exact approval/payment bindings and idempotently create the order."""
        return _execute(lambda: service.complete_checkout(request))

    @server.tool(name="get_order")
    def get_order(order_id: str) -> ToolResult:
        """Retrieve authoritative order and fulfillment state."""
        return _execute(lambda: service.get_order(order_id))

    @server.tool(name="get_order_by_checkout")
    def get_order_by_checkout(checkout_id: str) -> ToolResult:
        """Reconcile an ambiguous completion by finding the order for a checkout."""
        return _execute(lambda: service.get_order_by_checkout(checkout_id))

    @server.tool(name="cancel_order")
    def cancel_order(request: CancelOrderRequest) -> ToolResult:
        """Cancel an eligible order and emit payment-resolution events."""
        return _execute(lambda: service.cancel_order(request))

    @server.tool(name="create_return")
    def create_return(request: CreateReturnRequest) -> ToolResult:
        """Create an authorized return for eligible delivered order items."""
        return _execute(lambda: service.create_return(request))

    @server.tool(name="list_transaction_events")
    def list_transaction_events(transaction_id: str) -> ToolResult:
        """List the merchant events associated with one transaction."""
        return _execute(lambda: service.list_events(transaction_id))

    return server
