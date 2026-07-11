"""Deterministic and OpenAI Agents SDK implementations of agent judgment."""

from __future__ import annotations

import json
from datetime import date
from typing import Protocol

from agents import Agent, ModelSettings, RunConfig, Runner
from agents.mcp import create_static_tool_filter
from openai.types.shared import Reasoning
from openai.types.shared.reasoning_effort import ReasoningEffort
from pydantic import Field

from agent_commerce.commerce.models import Offer, SearchOffersRequest
from agent_commerce.orchestration.agent_mcp import CurrentMCPServerStreamableHttp
from agent_commerce.orchestration.merchant_gateway import MerchantGateway
from agent_commerce.orchestration.models import (
    NormalizedPurchaseIntent,
    OfferSelectionPlan,
    OrchestrationModel,
    RejectedOffer,
)


class IntentAttribute(OrchestrationModel):
    """Strict-schema representation of one requested product attribute."""

    name: str
    value: str | bool | int


class PurchaseIntentOutput(OrchestrationModel):
    """Model-facing intent schema without an arbitrary-key JSON object."""

    product_query: str
    category: str
    quantity: int = Field(gt=0)
    max_budget_minor: int | None = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    required_attributes: tuple[IntentAttribute, ...]
    latest_delivery_date: date | None
    minimum_return_window_days: int | None = Field(ge=0)
    purchase_if_confident: bool
    missing_required_fields: tuple[str, ...]
    clarification_questions: tuple[str, ...]


class IntentInterpreter(Protocol):
    async def normalize(self, raw_request: str) -> NormalizedPurchaseIntent: ...


class OfferPlanner(Protocol):
    async def select(self, intent: NormalizedPurchaseIntent) -> OfferSelectionPlan: ...


class DeterministicOfferPlanner:
    """Deterministic constraint evaluator over a merchant gateway."""

    def __init__(self, merchant: MerchantGateway) -> None:
        self.merchant = merchant

    async def select(self, intent: NormalizedPurchaseIntent) -> OfferSelectionPlan:
        offers = await self.merchant.search_offers(
            SearchOffersRequest(
                query=intent.product_query,
                currency=intent.currency,
                quantity=intent.quantity,
            )
        )
        eligible: list[tuple[int, Offer, str]] = []
        rejected: list[RejectedOffer] = []
        for offer in offers:
            reasons, delivery_id, total = self._evaluate(offer, intent)
            if reasons:
                rejected.append(RejectedOffer(offer_id=offer.offer_id, reasons=tuple(reasons)))
            elif delivery_id is not None:
                eligible.append((total, offer, delivery_id))
        if not eligible:
            reason = (
                f"No merchant catalog offers match '{intent.product_query}'."
                if not offers
                else "Relevant offers were found, but none satisfies every hard constraint."
            )
            return OfferSelectionPlan(
                selected_offer_id=None,
                confidence=1,
                selection_reason=reason,
                rejected_offers=tuple(rejected),
            )
        _, selected, delivery_id = min(eligible, key=lambda item: item[0])
        constraints = ["product relevance", "stock", "budget"]
        if intent.required_attributes:
            constraints.append("compatibility")
        if intent.latest_delivery_date:
            constraints.append("delivery")
        if intent.minimum_return_window_days is not None:
            constraints.append("returns")
        return OfferSelectionPlan(
            selected_offer_id=selected.offer_id,
            selected_offer_version=selected.version,
            delivery_option_id=delivery_id,
            confidence=0.98,
            selection_reason=(
                f"{selected.product.name} is the lowest-total eligible offer and satisfies "
                "all hard constraints."
            ),
            satisfied_constraints=tuple(constraints),
            rejected_offers=tuple(rejected),
        )

    @staticmethod
    def _evaluate(
        offer: Offer, intent: NormalizedPurchaseIntent
    ) -> tuple[list[str], str | None, int]:
        reasons: list[str] = []
        if offer.available_quantity < intent.quantity:
            reasons.append("Insufficient stock.")
        for key, expected in intent.required_attributes.items():
            if offer.product.attributes.get(key) != expected:
                reasons.append(f"Required attribute {key} is not satisfied.")
        if intent.minimum_return_window_days is not None and (
            not offer.return_policy.returnable
            or offer.return_policy.window_days < intent.minimum_return_window_days
        ):
            reasons.append("Return policy is below the required minimum.")
        delivery_options = list(offer.delivery_options)
        if intent.latest_delivery_date is not None:
            delivery_options = [
                option
                for option in delivery_options
                if option.estimated_delivery_date <= intent.latest_delivery_date
            ]
            if not delivery_options:
                reasons.append("No delivery option meets the deadline.")
        delivery = (
            min(delivery_options, key=lambda item: item.price_minor) if delivery_options else None
        )
        total = offer.unit_price.amount_minor * intent.quantity
        if delivery is not None:
            total += delivery.price_minor
        if intent.max_budget_minor is not None and total > intent.max_budget_minor:
            reasons.append("Total exceeds the budget.")
        return reasons, delivery.delivery_option_id if delivery else None, total


class OpenAIIntentInterpreter:
    """Structured intent extraction using the OpenAI Agents SDK."""

    def __init__(
        self,
        model: str,
        reasoning_effort: ReasoningEffort,
        *,
        today: date | None = None,
    ) -> None:
        self.today = today or date.today()
        self.agent = Agent(
            name="Purchase intent interpreter",
            model=model,
            model_settings=ModelSettings(
                reasoning=Reasoning(effort=reasoning_effort),
                verbosity="low",
            ),
            instructions=(
                "Convert the user's purchase request into the supplied structured schema. "
                "Amounts use integer minor units. Treat category and maximum budget/currency "
                "as required before an autonomous purchase. Do not invent missing values; "
                "list missing fields and concise clarification questions. Resolve relative "
                "dates only against the current date supplied with the request. Set "
                "product_query to a concise, product-focused search phrase, not the full user "
                "sentence. Infer category and arbitrary product attributes from meaning; do not "
                "rely on a fixed catalog or predefined product vocabulary."
            ),
            output_type=PurchaseIntentOutput,
        )

    async def normalize(self, raw_request: str) -> NormalizedPurchaseIntent:
        result = await Runner.run(
            self.agent,
            f"Current date: {self.today.isoformat()}\nPurchase request: {raw_request}",
            max_turns=2,
            run_config=RunConfig(
                workflow_name="commerce-intent-normalization",
                trace_include_sensitive_data=False,
            ),
        )
        output = result.final_output
        if not isinstance(output, PurchaseIntentOutput):
            raise RuntimeError("Intent agent returned an unexpected output type")
        return NormalizedPurchaseIntent(
            product_query=output.product_query,
            category=output.category,
            quantity=output.quantity,
            max_budget_minor=output.max_budget_minor,
            currency=output.currency,
            required_attributes={item.name: item.value for item in output.required_attributes},
            latest_delivery_date=output.latest_delivery_date,
            minimum_return_window_days=output.minimum_return_window_days,
            purchase_if_confident=output.purchase_if_confident,
            missing_required_fields=output.missing_required_fields,
            clarification_questions=output.clarification_questions,
        )


class OpenAIOfferPlanner:
    """Read-only offer discovery and selection through the merchant MCP server."""

    def __init__(
        self,
        model: str,
        mcp_url: str,
        reasoning_effort: ReasoningEffort,
    ) -> None:
        self.model = model
        self.mcp_url = mcp_url
        self.reasoning_effort = reasoning_effort

    async def select(self, intent: NormalizedPurchaseIntent) -> OfferSelectionPlan:
        tool_filter = create_static_tool_filter(
            allowed_tool_names=[
                "search_offers",
                "get_offer",
                "get_delivery_options",
                "get_return_policy",
            ]
        )
        server = CurrentMCPServerStreamableHttp(
            params={"url": self.mcp_url},
            cache_tools_list=True,
            tool_filter=tool_filter,
            use_structured_content=True,
        )
        async with server:
            agent = Agent(
                name="Commerce offer planner",
                model=self.model,
                model_settings=ModelSettings(
                    reasoning=Reasoning(effort=self.reasoning_effort),
                    verbosity="low",
                ),
                mcp_servers=[server],
                mcp_config={"convert_schemas_to_strict": True},
                instructions=(
                    "Use only the read-only merchant tools. Discover offers broadly enough to "
                    "explain rejected alternatives, enforce every hard constraint, calculate "
                    "the delivered total, and select an offer only when all hard constraints "
                    "are satisfied. Search by the intent's product meaning and attributes; never "
                    "assume a fixed product category. If an exhaustive search finds no suitable "
                    "offer, return no selection with high confidence and a concise explanation. "
                    "Never create or complete checkout in this planning step."
                ),
                output_type=OfferSelectionPlan,
            )
            result = await Runner.run(
                agent,
                "Select an offer for this normalized intent:\n"
                + json.dumps(intent.model_dump(mode="json"), indent=2),
                max_turns=8,
                run_config=RunConfig(
                    workflow_name="commerce-offer-discovery",
                    trace_include_sensitive_data=False,
                ),
            )
        if not isinstance(result.final_output, OfferSelectionPlan):
            raise RuntimeError("Offer planner returned an unexpected output type")
        return result.final_output
