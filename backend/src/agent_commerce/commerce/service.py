"""Merchant commerce application service shared by REST and MCP transports."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel

from agent_commerce.commerce.errors import CommerceError, conflict, not_found, validation_error
from agent_commerce.commerce.models import (
    ApprovalEvidence,
    CancelCheckoutRequest,
    CancelOrderRequest,
    Checkout,
    CheckoutLine,
    CheckoutState,
    CompleteCheckoutRequest,
    CreateCheckoutRequest,
    CreateReturnRequest,
    DeliveryOption,
    DomainEvent,
    Money,
    Offer,
    OfferSelection,
    Order,
    OrderState,
    PaymentAuthorizationReference,
    PriceBreakdown,
    ReturnPolicy,
    ReturnRecord,
    ReturnState,
    SearchOffersRequest,
    SetOrderStateRequest,
    UpdateCheckoutRequest,
)
from agent_commerce.commerce.repository import CommerceRepository, InMemoryCommerceRepository
from agent_commerce.commerce.seed import build_seed_offers

ModelT = TypeVar("ModelT", bound=BaseModel)
SEARCH_TOKEN_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)


def _search_tokens(value: str) -> set[str]:
    return set(SEARCH_TOKEN_PATTERN.findall(value.casefold().replace("_", " ")))


def _matches_product_query(offer: Offer, query: str) -> bool:
    requested = _search_tokens(query)
    if not requested:
        return False
    attributes = " ".join(f"{key} {value}" for key, value in offer.product.attributes.items())
    searchable = " ".join(
        (
            offer.product.name,
            offer.product.category,
            offer.product.brand,
            offer.product.description,
            offer.variant,
            attributes,
        )
    )
    return requested <= _search_tokens(searchable)


class CommerceService:
    """Authoritative merchant behavior with explicit state and idempotency checks."""

    def __init__(
        self,
        repository: CommerceRepository | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
        reservation_minutes: int = 15,
    ) -> None:
        self.repository = repository or InMemoryCommerceRepository()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self._reservation_duration = timedelta(minutes=reservation_minutes)
        self._event_handlers: list[Callable[[DomainEvent], None]] = []

    def add_event_handler(self, handler: Callable[[DomainEvent], None]) -> None:
        """Register an in-process consumer after the event is durably appended."""
        self._event_handlers.append(handler)

    @classmethod
    def with_seed_data(cls, *, now: datetime | None = None) -> CommerceService:
        seed_now = now or datetime.now(UTC)
        repository = InMemoryCommerceRepository()
        for offer in build_seed_offers(seed_now):
            repository.save_offer(offer)
        if now is None:
            return cls(repository)
        return cls(repository, clock=lambda: seed_now)

    def search_offers(self, request: SearchOffersRequest) -> list[Offer]:
        now = self._now()
        matches: list[Offer] = []
        for offer in self.repository.list_offers():
            if offer.expires_at <= now or offer.available_quantity < request.quantity:
                continue
            if offer.unit_price.currency != request.currency:
                continue
            if (
                request.category
                and offer.product.category.casefold() != request.category.casefold()
            ):
                continue
            if (
                request.max_unit_price_minor is not None
                and offer.unit_price.amount_minor > request.max_unit_price_minor
            ):
                continue
            if request.query and not _matches_product_query(offer, request.query):
                continue
            if any(
                offer.product.attributes.get(key) != value
                for key, value in request.required_attributes.items()
            ):
                continue
            if request.latest_delivery_date is not None and not any(
                option.estimated_delivery_date <= request.latest_delivery_date
                for option in offer.delivery_options
            ):
                continue
            if request.minimum_return_window_days is not None:
                if not offer.return_policy.returnable:
                    continue
                if offer.return_policy.window_days < request.minimum_return_window_days:
                    continue
            matches.append(offer)
        return sorted(matches, key=lambda item: item.unit_price.amount_minor)

    def get_offer(self, offer_id: str) -> Offer:
        offer = self.repository.get_offer(offer_id)
        if offer is None:
            raise not_found("offer", offer_id)
        return offer

    def create_checkout(self, request: CreateCheckoutRequest) -> Checkout:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "create_checkout", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, Checkout)

            offers = self._load_selected_offers(request.selections)
            self._validate_common_merchant_and_currency(offers)
            delivery = self._combined_delivery_option(offers, request.delivery_option_id)
            now = self._now()
            lines = self._build_lines(request.selections, offers)
            price = self._calculate_price(lines, delivery)
            return_policy = self._combined_return_policy(offers)

            for selection, offer in zip(request.selections, offers, strict=True):
                self.repository.save_offer(
                    offer.model_copy(
                        update={
                            "available_quantity": offer.available_quantity - selection.quantity,
                            "version": offer.version + 1,
                        }
                    )
                )

            checkout_id = f"chk_{self._id_factory()}"
            expires_at = now + self._reservation_duration
            checkout = Checkout(
                checkout_id=checkout_id,
                transaction_id=request.transaction_id,
                merchant_id=offers[0].merchant_id,
                version=1,
                state=CheckoutState.DRAFT,
                lines=tuple(lines),
                delivery_option=delivery,
                price=price,
                return_policy=return_policy,
                reserved_until=expires_at,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            self.repository.save_checkout(checkout)
            self._emit("checkout.created", checkout, checkout.model_dump(mode="json"))
            self.repository.save_idempotent(
                "create_checkout", request.idempotency_key, fingerprint, checkout
            )
            return checkout

    def get_checkout(self, checkout_id: str) -> Checkout:
        with self.repository.atomic():
            checkout = self.repository.get_checkout(checkout_id)
            if checkout is None:
                raise not_found("checkout", checkout_id)
            return self._expire_checkout_if_needed(checkout)

    def update_checkout(self, request: UpdateCheckoutRequest) -> Checkout:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "update_checkout", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, Checkout)

            checkout = self.get_checkout(request.checkout_id)
            self._require_draft_checkout(checkout, request.expected_version)
            selections = request.selections or tuple(
                OfferSelection(
                    offer_id=line.offer_id,
                    offer_version=self.get_offer(line.offer_id).version,
                    quantity=line.quantity,
                )
                for line in checkout.lines
            )
            offers = self._load_selected_offers_for_reallocation(checkout.lines, selections)
            self._validate_common_merchant_and_currency(offers)
            if offers[0].merchant_id != checkout.merchant_id:
                raise validation_error("Checkout merchant cannot be changed")
            delivery_option_id = (
                request.delivery_option_id or checkout.delivery_option.delivery_option_id
            )
            delivery = self._combined_delivery_option(offers, delivery_option_id)
            lines = self._build_lines(selections, offers)
            self._apply_inventory_reallocation(checkout.lines, selections)

            now = self._now()
            updated = checkout.model_copy(
                update={
                    "version": checkout.version + 1,
                    "lines": tuple(lines),
                    "delivery_option": delivery,
                    "price": self._calculate_price(lines, delivery),
                    "return_policy": self._combined_return_policy(offers),
                    "updated_at": now,
                }
            )
            self.repository.save_checkout(updated)
            self._emit("checkout.updated", updated, updated.model_dump(mode="json"))
            self.repository.save_idempotent(
                "update_checkout", request.idempotency_key, fingerprint, updated
            )
            return updated

    def cancel_checkout(self, request: CancelCheckoutRequest) -> Checkout:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "cancel_checkout", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, Checkout)
            checkout = self.get_checkout(request.checkout_id)
            self._require_draft_checkout(checkout, request.expected_version)
            self._release_inventory(checkout.lines)
            now = self._now()
            cancelled = checkout.model_copy(
                update={
                    "version": checkout.version + 1,
                    "state": CheckoutState.CANCELLED,
                    "updated_at": now,
                }
            )
            self.repository.save_checkout(cancelled)
            self._emit("checkout.cancelled", cancelled, {})
            self.repository.save_idempotent(
                "cancel_checkout", request.idempotency_key, fingerprint, cancelled
            )
            return cancelled

    def complete_checkout(self, request: CompleteCheckoutRequest) -> Order:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "complete_checkout", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, Order)
            checkout = self.get_checkout(request.checkout_id)
            self._require_draft_checkout(checkout, request.expected_version)
            self._validate_approval(checkout, request.approval)
            self._validate_payment_authorization(checkout, request.payment_authorization)

            existing = self.repository.get_order_by_checkout(checkout.checkout_id)
            if existing is not None:
                self.repository.save_idempotent(
                    "complete_checkout", request.idempotency_key, fingerprint, existing
                )
                return existing

            now = self._now()
            order = Order(
                order_id=f"ord_{self._id_factory()}",
                transaction_id=checkout.transaction_id,
                checkout_id=checkout.checkout_id,
                merchant_id=checkout.merchant_id,
                state=OrderState.CONFIRMED,
                lines=checkout.lines,
                delivery_option=checkout.delivery_option,
                price=checkout.price,
                return_policy=checkout.return_policy,
                payment_authorization_id=request.payment_authorization.payment_authorization_id,
                cancellable=True,
                returnable_until=(
                    checkout.delivery_option.estimated_delivery_date
                    + timedelta(days=checkout.return_policy.window_days)
                    if checkout.return_policy.returnable
                    else None
                ),
                created_at=now,
                updated_at=now,
            )
            completed_checkout = checkout.model_copy(
                update={
                    "version": checkout.version + 1,
                    "state": CheckoutState.COMPLETED,
                    "updated_at": now,
                }
            )
            self.repository.save_order(order)
            self.repository.save_checkout(completed_checkout)
            self._emit("order.confirmed", order, order.model_dump(mode="json"))
            self.repository.save_idempotent(
                "complete_checkout", request.idempotency_key, fingerprint, order
            )
            return order

    def get_order(self, order_id: str) -> Order:
        order = self.repository.get_order(order_id)
        if order is None:
            raise not_found("order", order_id)
        return order

    def get_order_by_checkout(self, checkout_id: str) -> Order:
        order = self.repository.get_order_by_checkout(checkout_id)
        if order is None:
            raise not_found("order_for_checkout", checkout_id)
        return order

    def cancel_order(self, request: CancelOrderRequest) -> Order:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "cancel_order", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, Order)
            order = self.get_order(request.order_id)
            if not order.cancellable or order.state not in {
                OrderState.CONFIRMED,
                OrderState.PROCESSING,
            }:
                raise CommerceError(
                    code="NOT_CANCELLABLE",
                    message="Order can no longer be cancelled",
                    details={"order_id": order.order_id, "state": order.state},
                )
            self._release_inventory(order.lines)
            now = self._now()
            cancelled = order.model_copy(
                update={
                    "state": OrderState.CANCELLED,
                    "cancellable": False,
                    "updated_at": now,
                }
            )
            self.repository.save_order(cancelled)
            self._emit(
                "order.cancelled",
                cancelled,
                {"payment_authorization_id": cancelled.payment_authorization_id},
            )
            self._emit(
                "refund.pending",
                cancelled,
                {
                    "amount_minor": cancelled.price.total_minor,
                    "currency": cancelled.price.currency,
                },
            )
            self.repository.save_idempotent(
                "cancel_order", request.idempotency_key, fingerprint, cancelled
            )
            return cancelled

    def set_order_state(self, request: SetOrderStateRequest) -> Order:
        """Merchant-side fulfillment transition used by deterministic demo controls."""
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "set_order_state", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, Order)
            order = self.get_order(request.order_id)
            allowed: dict[OrderState, set[OrderState]] = {
                OrderState.CONFIRMED: {OrderState.PROCESSING, OrderState.CANCELLED},
                OrderState.PROCESSING: {OrderState.SHIPPED, OrderState.CANCELLED},
                OrderState.SHIPPED: {OrderState.DELIVERED},
                OrderState.DELIVERED: set(),
                OrderState.CANCELLED: set(),
            }
            if request.state not in allowed[order.state]:
                raise conflict(
                    "Invalid order state transition",
                    order_id=order.order_id,
                    current_state=order.state,
                    requested_state=request.state,
                )
            now = self._now()
            updated = order.model_copy(
                update={
                    "state": request.state,
                    "cancellable": request.state
                    in {
                        OrderState.CONFIRMED,
                        OrderState.PROCESSING,
                    },
                    "updated_at": now,
                }
            )
            self.repository.save_order(updated)
            self._emit(
                "order.fulfillment_updated",
                updated,
                {"previous_state": order.state, "state": updated.state},
            )
            self.repository.save_idempotent(
                "set_order_state", request.idempotency_key, fingerprint, updated
            )
            return updated

    def create_return(self, request: CreateReturnRequest) -> ReturnRecord:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "create_return", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, ReturnRecord)
            order = self.get_order(request.order_id)
            if order.state is not OrderState.DELIVERED:
                raise CommerceError(
                    code="NOT_RETURNABLE",
                    message="Only delivered orders can be returned",
                    details={"order_id": order.order_id, "state": order.state},
                )
            if not order.return_policy.returnable or order.returnable_until is None:
                raise CommerceError(code="NOT_RETURNABLE", message="Order is not returnable")
            if self._now().date() > order.returnable_until:
                raise CommerceError(code="NOT_RETURNABLE", message="Return window has expired")

            line_by_product = {line.product_id: line for line in order.lines}
            refund_minor = 0
            for product_id, quantity in request.items.items():
                line = line_by_product.get(product_id)
                if line is None or quantity > line.quantity:
                    raise validation_error(
                        "Return item or quantity is invalid",
                        product_id=product_id,
                        quantity=quantity,
                    )
                refund_minor += line.unit_price.amount_minor * quantity
            refund_minor = max(0, refund_minor - order.return_policy.restocking_fee_minor)
            now = self._now()
            record = ReturnRecord(
                return_id=f"ret_{self._id_factory()}",
                order_id=order.order_id,
                transaction_id=order.transaction_id,
                state=ReturnState.AUTHORIZED,
                items=request.items,
                reason=request.reason,
                refund_amount=Money(
                    amount_minor=refund_minor,
                    currency=order.price.currency,
                ),
                created_at=now,
                updated_at=now,
            )
            self.repository.save_return(record)
            self._emit("return.created", record, record.model_dump(mode="json"))
            self._emit(
                "refund.pending",
                record,
                record.refund_amount.model_dump(mode="json"),
            )
            self.repository.save_idempotent(
                "create_return", request.idempotency_key, fingerprint, record
            )
            return record

    def list_events(self, transaction_id: str | None = None) -> list[DomainEvent]:
        return self.repository.list_events(transaction_id)

    def _load_selected_offers(self, selections: Iterable[OfferSelection]) -> list[Offer]:
        now = self._now()
        offers: list[Offer] = []
        for selection in selections:
            offer = self.get_offer(selection.offer_id)
            if offer.expires_at <= now:
                raise CommerceError(
                    code="EXPIRED",
                    message="Offer has expired",
                    details={"offer_id": offer.offer_id},
                )
            if offer.version != selection.offer_version:
                raise CommerceError(
                    code="STALE_VERSION",
                    message="Offer version is stale",
                    details={
                        "offer_id": offer.offer_id,
                        "expected_version": selection.offer_version,
                        "current_version": offer.version,
                    },
                )
            if offer.available_quantity < selection.quantity:
                raise CommerceError(
                    code="OUT_OF_STOCK",
                    message="Requested quantity is not available",
                    details={
                        "offer_id": offer.offer_id,
                        "requested": selection.quantity,
                        "available": offer.available_quantity,
                    },
                )
            offers.append(offer)
        return offers

    def _load_selected_offers_for_reallocation(
        self,
        current_lines: Iterable[CheckoutLine],
        selections: Iterable[OfferSelection],
    ) -> list[Offer]:
        reserved = {line.offer_id: line.quantity for line in current_lines}
        now = self._now()
        offers: list[Offer] = []
        for selection in selections:
            offer = self.get_offer(selection.offer_id)
            if offer.expires_at <= now:
                raise CommerceError(
                    code="EXPIRED",
                    message="Offer has expired",
                    details={"offer_id": offer.offer_id},
                )
            if offer.version != selection.offer_version:
                raise CommerceError(
                    code="STALE_VERSION",
                    message="Offer version is stale",
                    details={
                        "offer_id": offer.offer_id,
                        "expected_version": selection.offer_version,
                        "current_version": offer.version,
                    },
                )
            effective_available = offer.available_quantity + reserved.get(offer.offer_id, 0)
            if effective_available < selection.quantity:
                raise CommerceError(
                    code="OUT_OF_STOCK",
                    message="Requested quantity is not available",
                    details={
                        "offer_id": offer.offer_id,
                        "requested": selection.quantity,
                        "available": effective_available,
                    },
                )
            offers.append(offer)
        return offers

    def _apply_inventory_reallocation(
        self,
        current_lines: Iterable[CheckoutLine],
        selections: Iterable[OfferSelection],
    ) -> None:
        old_quantities = {line.offer_id: line.quantity for line in current_lines}
        new_quantities = {selection.offer_id: selection.quantity for selection in selections}
        for offer_id in old_quantities.keys() | new_quantities.keys():
            offer = self.get_offer(offer_id)
            available = (
                offer.available_quantity
                + old_quantities.get(offer_id, 0)
                - new_quantities.get(offer_id, 0)
            )
            if available < 0:
                raise CommerceError(
                    code="RECOVERY_REQUIRED",
                    message="Inventory reallocation became inconsistent",
                    details={"offer_id": offer_id},
                )
            self.repository.save_offer(
                offer.model_copy(
                    update={"available_quantity": available, "version": offer.version + 1}
                )
            )

    @staticmethod
    def _validate_common_merchant_and_currency(offers: list[Offer]) -> None:
        if not offers:
            raise validation_error("At least one offer is required")
        merchants = {offer.merchant_id for offer in offers}
        currencies = {offer.unit_price.currency for offer in offers}
        if len(merchants) != 1:
            raise validation_error("One checkout cannot contain multiple merchants")
        if len(currencies) != 1:
            raise validation_error("One checkout cannot contain multiple currencies")

    @staticmethod
    def _combined_delivery_option(offers: list[Offer], delivery_option_id: str) -> DeliveryOption:
        selected: list[DeliveryOption] = []
        for offer in offers:
            option = next(
                (
                    candidate
                    for candidate in offer.delivery_options
                    if candidate.delivery_option_id == delivery_option_id
                ),
                None,
            )
            if option is None:
                raise validation_error(
                    "Delivery option is not available for every selected offer",
                    offer_id=offer.offer_id,
                    delivery_option_id=delivery_option_id,
                )
            selected.append(option)
        return DeliveryOption(
            delivery_option_id=delivery_option_id,
            label=selected[0].label,
            price_minor=max(option.price_minor for option in selected),
            estimated_delivery_date=max(option.estimated_delivery_date for option in selected),
        )

    @staticmethod
    def _build_lines(
        selections: Iterable[OfferSelection], offers: Iterable[Offer]
    ) -> list[CheckoutLine]:
        return [
            CheckoutLine(
                offer_id=offer.offer_id,
                offer_version=offer.version,
                product_id=offer.product.product_id,
                product_name=offer.product.name,
                product_category=offer.product.category,
                variant=offer.variant,
                quantity=selection.quantity,
                unit_price=offer.unit_price,
                line_total_minor=offer.unit_price.amount_minor * selection.quantity,
            )
            for selection, offer in zip(selections, offers, strict=True)
        ]

    @staticmethod
    def _calculate_price(lines: Iterable[CheckoutLine], delivery: DeliveryOption) -> PriceBreakdown:
        lines_tuple = tuple(lines)
        subtotal = sum(line.line_total_minor for line in lines_tuple)
        total = subtotal + delivery.price_minor
        tax_included = round(total * 23 / 123)
        currency = lines_tuple[0].unit_price.currency
        return PriceBreakdown(
            subtotal_minor=subtotal,
            shipping_minor=delivery.price_minor,
            tax_minor=tax_included,
            total_minor=total,
            currency=currency,
            tax_included=True,
        )

    @staticmethod
    def _combined_return_policy(offers: list[Offer]) -> ReturnPolicy:
        returnable = all(offer.return_policy.returnable for offer in offers)
        window = min(offer.return_policy.window_days for offer in offers) if returnable else 0
        fee = sum(offer.return_policy.restocking_fee_minor for offer in offers)
        return ReturnPolicy(
            returnable=returnable,
            window_days=window,
            restocking_fee_minor=fee,
            description=(
                f"All items returnable within {window} days."
                if returnable
                else "At least one selected item is not returnable."
            ),
        )

    def _require_draft_checkout(self, checkout: Checkout, expected_version: int) -> None:
        if checkout.version != expected_version:
            raise CommerceError(
                code="STALE_VERSION",
                message="Checkout version is stale",
                details={
                    "checkout_id": checkout.checkout_id,
                    "expected_version": expected_version,
                    "current_version": checkout.version,
                },
            )
        if checkout.state is CheckoutState.EXPIRED:
            raise CommerceError(code="EXPIRED", message="Checkout has expired")
        if checkout.state is not CheckoutState.DRAFT:
            raise conflict(
                "Checkout is not mutable",
                checkout_id=checkout.checkout_id,
                state=checkout.state,
            )

    def _expire_checkout_if_needed(self, checkout: Checkout) -> Checkout:
        if checkout.state is CheckoutState.DRAFT and checkout.expires_at <= self._now():
            self._release_inventory(checkout.lines)
            expired = checkout.model_copy(
                update={
                    "version": checkout.version + 1,
                    "state": CheckoutState.EXPIRED,
                    "updated_at": self._now(),
                }
            )
            self.repository.save_checkout(expired)
            self._emit("checkout.expired", expired, {})
            return expired
        return checkout

    def _release_inventory(self, lines: Iterable[CheckoutLine]) -> None:
        for line in lines:
            offer = self.get_offer(line.offer_id)
            self.repository.save_offer(
                offer.model_copy(
                    update={
                        "available_quantity": offer.available_quantity + line.quantity,
                        "version": offer.version + 1,
                    }
                )
            )

    def _validate_approval(self, checkout: Checkout, approval: ApprovalEvidence) -> None:
        self._validate_authority_binding(
            checkout,
            approval.checkout_id,
            approval.checkout_version,
            approval.merchant_id,
            approval.amount_minor,
            approval.currency,
            approval.expires_at,
            authority="approval",
        )

    def _validate_payment_authorization(
        self, checkout: Checkout, authorization: PaymentAuthorizationReference
    ) -> None:
        self._validate_authority_binding(
            checkout,
            authorization.checkout_id,
            authorization.checkout_version,
            authorization.merchant_id,
            authorization.amount_minor,
            authorization.currency,
            authorization.expires_at,
            authority="payment authorization",
        )

    def _validate_authority_binding(
        self,
        checkout: Checkout,
        checkout_id: str,
        checkout_version: int,
        merchant_id: str,
        amount_minor: int,
        currency: str,
        expires_at: datetime,
        *,
        authority: str,
    ) -> None:
        expected = {
            "checkout_id": checkout.checkout_id,
            "checkout_version": checkout.version,
            "merchant_id": checkout.merchant_id,
            "amount_minor": checkout.price.total_minor,
            "currency": checkout.price.currency,
        }
        actual = {
            "checkout_id": checkout_id,
            "checkout_version": checkout_version,
            "merchant_id": merchant_id,
            "amount_minor": amount_minor,
            "currency": currency,
        }
        if expected != actual or expires_at <= self._now():
            raise CommerceError(
                code="APPROVAL_INVALID" if authority == "approval" else "PAYMENT_DECLINED",
                message=f"{authority.title()} does not match the current checkout",
                details={"expected": expected, "actual": actual},
            )

    def _emit(
        self,
        event_type: str,
        subject: Checkout | Order | ReturnRecord,
        payload: dict[str, object],
    ) -> None:
        transaction_id = subject.transaction_id
        subject_id = next(
            getattr(subject, field)
            for field in ("return_id", "order_id", "checkout_id")
            if hasattr(subject, field)
        )
        event = DomainEvent(
            event_id=f"evt_{self._id_factory()}",
            event_type=event_type,
            occurred_at=self._now(),
            correlation_id=transaction_id,
            transaction_id=transaction_id,
            subject_type=subject.__class__.__name__.lower(),
            subject_id=subject_id,
            subject_version=getattr(subject, "version", None),
            payload=payload,
        )
        self.repository.append_event(event)
        for handler in self._event_handlers:
            handler(event)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise RuntimeError("Commerce clock must return a timezone-aware datetime")
        return value

    @staticmethod
    def _fingerprint(request: BaseModel) -> str:
        canonical = request.model_dump_json(exclude={"idempotency_key"})
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _expect_type(value: object, expected: type[ModelT]) -> ModelT:
        if not isinstance(value, expected):
            raise RuntimeError(f"Corrupt idempotency record: expected {expected.__name__}")
        return value
