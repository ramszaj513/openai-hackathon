"""Agent-friendly request contracts specific to the merchant MCP boundary."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from agent_commerce.commerce.models import SearchOffersRequest


class MCPContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AttributeConstraint(MCPContractModel):
    """One portable product-attribute constraint."""

    name: str = Field(min_length=1)
    value: str | bool | int


class SearchOffersToolRequest(MCPContractModel):
    """Strict-schema-compatible MCP representation of an offer search."""

    query: str | None = None
    category: str | None = None
    max_unit_price_minor: int | None = Field(default=None, ge=0)
    currency: str = Field(default="PLN", pattern=r"^[A-Z]{3}$")
    required_attributes: tuple[AttributeConstraint, ...] = ()
    latest_delivery_date: date | None = None
    minimum_return_window_days: int | None = Field(default=None, ge=0)
    quantity: int = Field(default=1, gt=0)

    def to_domain(self) -> SearchOffersRequest:
        return SearchOffersRequest(
            query=self.query,
            category=self.category,
            max_unit_price_minor=self.max_unit_price_minor,
            currency=self.currency,
            required_attributes={item.name: item.value for item in self.required_attributes},
            latest_delivery_date=self.latest_delivery_date,
            minimum_return_window_days=self.minimum_return_window_days,
            quantity=self.quantity,
        )

    @classmethod
    def from_domain(cls, request: SearchOffersRequest) -> SearchOffersToolRequest:
        return cls(
            query=request.query,
            category=request.category,
            max_unit_price_minor=request.max_unit_price_minor,
            currency=request.currency,
            required_attributes=tuple(
                AttributeConstraint(name=name, value=value)
                for name, value in request.required_attributes.items()
            ),
            latest_delivery_date=request.latest_delivery_date,
            minimum_return_window_days=request.minimum_return_window_days,
            quantity=request.quantity,
        )
