"""Typed merchant contracts used by application, REST, and MCP layers."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MinorAmount = Annotated[int, Field(ge=0)]
PositiveQuantity = Annotated[int, Field(gt=0)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CheckoutState(StrEnum):
    DRAFT = "DRAFT"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class OrderState(StrEnum):
    CONFIRMED = "CONFIRMED"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class ReturnState(StrEnum):
    REQUESTED = "REQUESTED"
    AUTHORIZED = "AUTHORIZED"
    RECEIVED = "RECEIVED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class Money(ContractModel):
    amount_minor: MinorAmount
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class PriceBreakdown(ContractModel):
    subtotal_minor: MinorAmount
    discount_minor: MinorAmount = 0
    shipping_minor: MinorAmount = 0
    tax_minor: MinorAmount = 0
    fees_minor: MinorAmount = 0
    total_minor: MinorAmount
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    tax_included: bool = True

    @model_validator(mode="after")
    def validate_total(self) -> PriceBreakdown:
        expected = self.subtotal_minor - self.discount_minor + self.shipping_minor + self.fees_minor
        if not self.tax_included:
            expected += self.tax_minor
        if expected != self.total_minor:
            raise ValueError(f"total_minor must equal {expected}")
        return self


class ReturnPolicy(ContractModel):
    returnable: bool
    window_days: int = Field(ge=0)
    restocking_fee_minor: MinorAmount = 0
    description: str


class DeliveryOption(ContractModel):
    delivery_option_id: str
    label: str
    price_minor: MinorAmount
    estimated_delivery_date: date


class Product(ContractModel):
    product_id: str
    name: str
    category: str
    brand: str
    description: str
    attributes: dict[str, str | bool | int]


class Offer(ContractModel):
    offer_id: str
    merchant_id: str
    product: Product
    variant: str
    unit_price: Money
    available_quantity: int = Field(ge=0)
    delivery_options: tuple[DeliveryOption, ...]
    return_policy: ReturnPolicy
    version: int = Field(ge=1)
    expires_at: datetime


class CheckoutLine(ContractModel):
    offer_id: str
    offer_version: int = Field(ge=1)
    product_id: str
    product_name: str
    product_category: str
    variant: str
    quantity: PositiveQuantity
    unit_price: Money
    line_total_minor: MinorAmount


class Checkout(ContractModel):
    checkout_id: str
    transaction_id: str
    merchant_id: str
    version: int = Field(ge=1)
    state: CheckoutState
    lines: tuple[CheckoutLine, ...]
    delivery_option: DeliveryOption
    price: PriceBreakdown
    return_policy: ReturnPolicy
    reserved_until: datetime
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class Order(ContractModel):
    order_id: str
    transaction_id: str
    checkout_id: str
    merchant_id: str
    state: OrderState
    lines: tuple[CheckoutLine, ...]
    delivery_option: DeliveryOption
    price: PriceBreakdown
    return_policy: ReturnPolicy
    payment_authorization_id: str
    cancellable: bool
    returnable_until: date | None
    created_at: datetime
    updated_at: datetime


class ReturnRecord(ContractModel):
    return_id: str
    order_id: str
    transaction_id: str
    state: ReturnState
    items: dict[str, PositiveQuantity]
    reason: str
    refund_amount: Money
    created_at: datetime
    updated_at: datetime


class DomainEvent(ContractModel):
    event_id: str
    event_type: str
    occurred_at: datetime
    correlation_id: str
    transaction_id: str
    subject_type: str
    subject_id: str
    subject_version: int | None = None
    payload: dict[str, Any]


class SearchOffersRequest(ContractModel):
    query: str | None = None
    category: str | None = None
    max_unit_price_minor: MinorAmount | None = None
    currency: str = Field(default="PLN", pattern=r"^[A-Z]{3}$")
    required_attributes: dict[str, str | bool | int] = Field(default_factory=dict)
    latest_delivery_date: date | None = None
    minimum_return_window_days: int | None = Field(default=None, ge=0)
    quantity: PositiveQuantity = 1


class OfferSelection(ContractModel):
    offer_id: str
    offer_version: int = Field(ge=1)
    quantity: PositiveQuantity


class CreateCheckoutRequest(ContractModel):
    transaction_id: str
    selections: tuple[OfferSelection, ...] = Field(min_length=1)
    delivery_option_id: str
    idempotency_key: str

    @model_validator(mode="after")
    def require_unique_offers(self) -> CreateCheckoutRequest:
        offer_ids = [selection.offer_id for selection in self.selections]
        if len(offer_ids) != len(set(offer_ids)):
            raise ValueError("Each offer may appear only once in a checkout")
        return self


class UpdateCheckoutRequest(ContractModel):
    checkout_id: str
    expected_version: int = Field(ge=1)
    selections: tuple[OfferSelection, ...] | None = None
    delivery_option_id: str | None = None
    idempotency_key: str

    @model_validator(mode="after")
    def require_change(self) -> UpdateCheckoutRequest:
        if self.selections is None and self.delivery_option_id is None:
            raise ValueError("At least one checkout change is required")
        if self.selections is not None:
            if not self.selections:
                raise ValueError("Checkout must retain at least one offer")
            offer_ids = [selection.offer_id for selection in self.selections]
            if len(offer_ids) != len(set(offer_ids)):
                raise ValueError("Each offer may appear only once in a checkout")
        return self


class ApprovalEvidence(ContractModel):
    approval_id: str
    checkout_id: str
    checkout_version: int = Field(ge=1)
    merchant_id: str
    amount_minor: MinorAmount
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    expires_at: datetime


class PaymentAuthorizationReference(ContractModel):
    payment_authorization_id: str
    checkout_id: str
    checkout_version: int = Field(ge=1)
    merchant_id: str
    amount_minor: MinorAmount
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: Literal["AUTHORIZED"] = "AUTHORIZED"
    expires_at: datetime


class CompleteCheckoutRequest(ContractModel):
    checkout_id: str
    expected_version: int = Field(ge=1)
    approval: ApprovalEvidence
    payment_authorization: PaymentAuthorizationReference
    idempotency_key: str


class CancelCheckoutRequest(ContractModel):
    checkout_id: str
    expected_version: int = Field(ge=1)
    idempotency_key: str


class CancelOrderRequest(ContractModel):
    order_id: str
    idempotency_key: str


class CreateReturnRequest(ContractModel):
    order_id: str
    items: dict[str, PositiveQuantity] = Field(min_length=1)
    reason: str = Field(min_length=3)
    idempotency_key: str


class SetOrderStateRequest(ContractModel):
    order_id: str
    state: OrderState
    idempotency_key: str


class ToolResult(ContractModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
