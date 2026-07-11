"""Merchant gateway abstractions for direct tests and real MCP transport."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Protocol, TypeVar

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel, TypeAdapter

from agent_commerce.commerce.errors import CommerceError
from agent_commerce.commerce.models import (
    CancelOrderRequest,
    Checkout,
    CompleteCheckoutRequest,
    CreateCheckoutRequest,
    CreateReturnRequest,
    DomainEvent,
    Offer,
    Order,
    ReturnRecord,
    SearchOffersRequest,
)
from agent_commerce.commerce.service import CommerceService

ModelT = TypeVar("ModelT", bound=BaseModel)


class AmbiguousMerchantError(RuntimeError):
    """The request outcome is unknown and must be reconciled before retry."""


class MerchantGateway(Protocol):
    async def search_offers(self, request: SearchOffersRequest) -> list[Offer]: ...

    async def get_offer(self, offer_id: str) -> Offer: ...

    async def create_checkout(self, request: CreateCheckoutRequest) -> Checkout: ...

    async def get_checkout(self, checkout_id: str) -> Checkout: ...

    async def complete_checkout(self, request: CompleteCheckoutRequest) -> Order: ...

    async def get_order(self, order_id: str) -> Order: ...

    async def get_order_by_checkout(self, checkout_id: str) -> Order: ...

    async def cancel_order(self, request: CancelOrderRequest) -> Order: ...

    async def create_return(self, request: CreateReturnRequest) -> ReturnRecord: ...

    async def list_events(self, transaction_id: str) -> list[DomainEvent]: ...


class DirectMerchantGateway:
    """Direct adapter for deterministic tests; production uses MCPMerchantGateway."""

    def __init__(self, service: CommerceService) -> None:
        self.service = service

    async def search_offers(self, request: SearchOffersRequest) -> list[Offer]:
        return self.service.search_offers(request)

    async def get_offer(self, offer_id: str) -> Offer:
        return self.service.get_offer(offer_id)

    async def create_checkout(self, request: CreateCheckoutRequest) -> Checkout:
        return self.service.create_checkout(request)

    async def get_checkout(self, checkout_id: str) -> Checkout:
        return self.service.get_checkout(checkout_id)

    async def complete_checkout(self, request: CompleteCheckoutRequest) -> Order:
        return self.service.complete_checkout(request)

    async def get_order(self, order_id: str) -> Order:
        return self.service.get_order(order_id)

    async def get_order_by_checkout(self, checkout_id: str) -> Order:
        return self.service.get_order_by_checkout(checkout_id)

    async def cancel_order(self, request: CancelOrderRequest) -> Order:
        return self.service.cancel_order(request)

    async def create_return(self, request: CreateReturnRequest) -> ReturnRecord:
        return self.service.create_return(request)

    async def list_events(self, transaction_id: str) -> list[DomainEvent]:
        return self.service.list_events(transaction_id)


class MCPMerchantGateway:
    """Typed client for the external merchant's Streamable HTTP MCP endpoint."""

    def __init__(self, url: str, *, timeout_seconds: float = 10) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds

    async def search_offers(self, request: SearchOffersRequest) -> list[Offer]:
        payload = await self._call("search_offers", {"request": request.model_dump(mode="json")})
        return TypeAdapter(list[Offer]).validate_python(payload)

    async def get_offer(self, offer_id: str) -> Offer:
        return Offer.model_validate(await self._call("get_offer", {"offer_id": offer_id}))

    async def create_checkout(self, request: CreateCheckoutRequest) -> Checkout:
        payload = await self._call("create_checkout", {"request": request.model_dump(mode="json")})
        return Checkout.model_validate(payload)

    async def get_checkout(self, checkout_id: str) -> Checkout:
        payload = await self._call("get_checkout", {"checkout_id": checkout_id})
        return Checkout.model_validate(payload)

    async def complete_checkout(self, request: CompleteCheckoutRequest) -> Order:
        try:
            payload = await self._call(
                "complete_checkout", {"request": request.model_dump(mode="json")}
            )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise AmbiguousMerchantError("Merchant completion timed out") from exc
        return Order.model_validate(payload)

    async def get_order(self, order_id: str) -> Order:
        return Order.model_validate(await self._call("get_order", {"order_id": order_id}))

    async def get_order_by_checkout(self, checkout_id: str) -> Order:
        payload = await self._call("get_order_by_checkout", {"checkout_id": checkout_id})
        return Order.model_validate(payload)

    async def cancel_order(self, request: CancelOrderRequest) -> Order:
        payload = await self._call("cancel_order", {"request": request.model_dump(mode="json")})
        return Order.model_validate(payload)

    async def create_return(self, request: CreateReturnRequest) -> ReturnRecord:
        payload = await self._call("create_return", {"request": request.model_dump(mode="json")})
        return ReturnRecord.model_validate(payload)

    async def list_events(self, transaction_id: str) -> list[DomainEvent]:
        payload = await self._call("list_transaction_events", {"transaction_id": transaction_id})
        return TypeAdapter(list[DomainEvent]).validate_python(payload)

    async def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        timeout = httpx.Timeout(self.timeout_seconds)
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            streamable_http_client(self.url, http_client=client) as streams,
        ):
            read_stream, write_stream, _ = streams
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=self.timeout_seconds),
            ) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
        structured = result.structuredContent
        if not isinstance(structured, dict):
            raise RuntimeError(f"MCP tool {name} did not return structured content")
        if not structured.get("ok"):
            error = structured.get("error")
            if not isinstance(error, dict):
                raise RuntimeError(f"MCP tool {name} returned an invalid error")
            raise CommerceError(
                code=str(error.get("code", "TEMPORARILY_UNAVAILABLE")),
                message=str(error.get("message", "Merchant tool failed")),
                details=error.get("details") if isinstance(error.get("details"), dict) else None,
            )
        data = structured.get("data")
        if not isinstance(data, dict) or "result" not in data:
            raise RuntimeError(f"MCP tool {name} returned invalid data")
        return data["result"]
