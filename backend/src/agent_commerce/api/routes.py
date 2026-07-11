"""Commerce REST routes backed by the same services as FastMCP."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_commerce.commerce.models import (
    CancelCheckoutRequest,
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
    SetOrderStateRequest,
    UpdateCheckoutRequest,
)
from agent_commerce.commerce.service import CommerceService


def create_commerce_router(service: CommerceService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["commerce"])

    def get_service() -> CommerceService:
        return service

    Service = Depends(get_service)

    @router.post("/offers/search", response_model=list[Offer])
    def search_offers(
        request: SearchOffersRequest, commerce: CommerceService = Service
    ) -> list[Offer]:
        return commerce.search_offers(request)

    @router.get("/offers/{offer_id}", response_model=Offer)
    def get_offer(offer_id: str, commerce: CommerceService = Service) -> Offer:
        return commerce.get_offer(offer_id)

    @router.post("/checkouts", response_model=Checkout, status_code=201)
    def create_checkout(
        request: CreateCheckoutRequest, commerce: CommerceService = Service
    ) -> Checkout:
        return commerce.create_checkout(request)

    @router.get("/checkouts/{checkout_id}", response_model=Checkout)
    def get_checkout(checkout_id: str, commerce: CommerceService = Service) -> Checkout:
        return commerce.get_checkout(checkout_id)

    @router.put("/checkouts/{checkout_id}", response_model=Checkout)
    def update_checkout(
        checkout_id: str,
        request: UpdateCheckoutRequest,
        commerce: CommerceService = Service,
    ) -> Checkout:
        if request.checkout_id != checkout_id:
            from agent_commerce.commerce.errors import validation_error

            raise validation_error("Path checkout_id does not match request checkout_id")
        return commerce.update_checkout(request)

    @router.post("/checkouts/{checkout_id}/cancel", response_model=Checkout)
    def cancel_checkout(
        checkout_id: str,
        request: CancelCheckoutRequest,
        commerce: CommerceService = Service,
    ) -> Checkout:
        if request.checkout_id != checkout_id:
            from agent_commerce.commerce.errors import validation_error

            raise validation_error("Path checkout_id does not match request checkout_id")
        return commerce.cancel_checkout(request)

    @router.post("/checkouts/{checkout_id}/complete", response_model=Order)
    def complete_checkout(
        checkout_id: str,
        request: CompleteCheckoutRequest,
        commerce: CommerceService = Service,
    ) -> Order:
        if request.checkout_id != checkout_id:
            from agent_commerce.commerce.errors import validation_error

            raise validation_error("Path checkout_id does not match request checkout_id")
        return commerce.complete_checkout(request)

    @router.get("/orders/{order_id}", response_model=Order)
    def get_order(order_id: str, commerce: CommerceService = Service) -> Order:
        return commerce.get_order(order_id)

    @router.get("/checkouts/{checkout_id}/order", response_model=Order)
    def get_order_by_checkout(checkout_id: str, commerce: CommerceService = Service) -> Order:
        return commerce.get_order_by_checkout(checkout_id)

    @router.post("/orders/{order_id}/cancel", response_model=Order)
    def cancel_order(
        order_id: str,
        request: CancelOrderRequest,
        commerce: CommerceService = Service,
    ) -> Order:
        if request.order_id != order_id:
            from agent_commerce.commerce.errors import validation_error

            raise validation_error("Path order_id does not match request order_id")
        return commerce.cancel_order(request)

    @router.post("/orders/{order_id}/returns", response_model=ReturnRecord, status_code=201)
    def create_return(
        order_id: str,
        request: CreateReturnRequest,
        commerce: CommerceService = Service,
    ) -> ReturnRecord:
        if request.order_id != order_id:
            from agent_commerce.commerce.errors import validation_error

            raise validation_error("Path order_id does not match request order_id")
        return commerce.create_return(request)

    @router.post("/demo/orders/{order_id}/state", response_model=Order)
    def set_order_state(
        order_id: str,
        request: SetOrderStateRequest,
        commerce: CommerceService = Service,
    ) -> Order:
        if request.order_id != order_id:
            from agent_commerce.commerce.errors import validation_error

            raise validation_error("Path order_id does not match request order_id")
        return commerce.set_order_state(request)

    @router.get("/transactions/{transaction_id}/events", response_model=list[DomainEvent])
    def list_events(transaction_id: str, commerce: CommerceService = Service) -> list[DomainEvent]:
        return commerce.list_events(transaction_id)

    return router
