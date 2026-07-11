"""Repository contracts and deterministic in-memory implementation."""

from __future__ import annotations

from contextlib import AbstractContextManager
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol, TypeVar

from agent_commerce.commerce.models import (
    Checkout,
    DomainEvent,
    Offer,
    Order,
    ReturnRecord,
)

T = TypeVar("T")


class CommerceRepository(Protocol):
    def list_offers(self) -> list[Offer]: ...

    def get_offer(self, offer_id: str) -> Offer | None: ...

    def save_offer(self, offer: Offer) -> None: ...

    def get_checkout(self, checkout_id: str) -> Checkout | None: ...

    def save_checkout(self, checkout: Checkout) -> None: ...

    def get_order(self, order_id: str) -> Order | None: ...

    def get_order_by_checkout(self, checkout_id: str) -> Order | None: ...

    def save_order(self, order: Order) -> None: ...

    def get_return(self, return_id: str) -> ReturnRecord | None: ...

    def save_return(self, record: ReturnRecord) -> None: ...

    def append_event(self, event: DomainEvent) -> None: ...

    def list_events(self, transaction_id: str | None = None) -> list[DomainEvent]: ...

    def get_idempotent(self, operation: str, key: str, fingerprint: str) -> Any | None: ...

    def save_idempotent(self, operation: str, key: str, fingerprint: str, value: Any) -> None: ...

    def atomic(self) -> AbstractContextManager[bool]: ...


@dataclass
class InMemoryCommerceRepository:
    """Thread-safe repository for local development and deterministic tests."""

    offers: dict[str, Offer] = field(default_factory=dict)
    checkouts: dict[str, Checkout] = field(default_factory=dict)
    orders: dict[str, Order] = field(default_factory=dict)
    returns: dict[str, ReturnRecord] = field(default_factory=dict)
    events: list[DomainEvent] = field(default_factory=list)
    idempotency: dict[tuple[str, str], tuple[str, Any]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def atomic(self) -> AbstractContextManager[bool]:
        return self._lock

    def list_offers(self) -> list[Offer]:
        return deepcopy(list(self.offers.values()))

    def get_offer(self, offer_id: str) -> Offer | None:
        value = self.offers.get(offer_id)
        return deepcopy(value) if value else None

    def save_offer(self, offer: Offer) -> None:
        self.offers[offer.offer_id] = deepcopy(offer)

    def get_checkout(self, checkout_id: str) -> Checkout | None:
        value = self.checkouts.get(checkout_id)
        return deepcopy(value) if value else None

    def save_checkout(self, checkout: Checkout) -> None:
        self.checkouts[checkout.checkout_id] = deepcopy(checkout)

    def get_order(self, order_id: str) -> Order | None:
        value = self.orders.get(order_id)
        return deepcopy(value) if value else None

    def get_order_by_checkout(self, checkout_id: str) -> Order | None:
        for order in self.orders.values():
            if order.checkout_id == checkout_id:
                return deepcopy(order)
        return None

    def save_order(self, order: Order) -> None:
        self.orders[order.order_id] = deepcopy(order)

    def get_return(self, return_id: str) -> ReturnRecord | None:
        value = self.returns.get(return_id)
        return deepcopy(value) if value else None

    def save_return(self, record: ReturnRecord) -> None:
        self.returns[record.return_id] = deepcopy(record)

    def append_event(self, event: DomainEvent) -> None:
        self.events.append(deepcopy(event))

    def list_events(self, transaction_id: str | None = None) -> list[DomainEvent]:
        events = self.events
        if transaction_id is not None:
            events = [event for event in events if event.transaction_id == transaction_id]
        return deepcopy(events)

    def get_idempotent(self, operation: str, key: str, fingerprint: str) -> Any | None:
        stored = self.idempotency.get((operation, key))
        if stored is None:
            return None
        stored_fingerprint, value = stored
        if stored_fingerprint != fingerprint:
            from agent_commerce.commerce.errors import CommerceError

            raise CommerceError(
                code="IDEMPOTENCY_CONFLICT",
                message="Idempotency key was reused with a different request",
                details={"operation": operation, "idempotency_key": key},
            )
        return deepcopy(value)

    def save_idempotent(self, operation: str, key: str, fingerprint: str, value: Any) -> None:
        self.idempotency[(operation, key)] = (fingerprint, deepcopy(value))
