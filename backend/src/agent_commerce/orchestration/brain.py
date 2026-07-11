"""Deterministic and OpenAI Agents SDK implementations of agent judgment."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

from agents import (
    Agent,
    ModelResponse,
    ModelSettings,
    RunConfig,
    RunContextWrapper,
    RunHooks,
    Runner,
    Tool,
)
from openai.types.shared import Reasoning
from openai.types.shared.reasoning_effort import ReasoningEffort
from pydantic import Field

from agent_commerce.commerce.models import Offer, SearchOffersRequest
from agent_commerce.orchestration.activity import (
    ActivityPhase,
    ActivityReporter,
    ActivityStatus,
)
from agent_commerce.orchestration.merchant_gateway import MerchantGateway
from agent_commerce.orchestration.models import (
    DisplayParameter,
    NormalizedPurchaseIntent,
    OfferSelectionPlan,
    OrchestrationModel,
    RejectedOffer,
)

AGENT_LOG_PATH = Path(__file__).resolve().parents[4] / "agent_log"


def _log_agent_exchange(agent_name: str, request: str, response: OrchestrationModel) -> None:
    """Append one safe, structured model exchange to the repository-local agent log."""
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "agent": agent_name,
        "request": request,
        "response": response.model_dump(mode="json"),
    }
    with AGENT_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")


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


class OfferMatchAssessment(OrchestrationModel):
    """One model judgment comparing a candidate with the requested product meaning."""

    offer_id: str
    matches: bool
    confidence: float = Field(ge=0, le=1)
    reason: str


class OfferComparisonOutput(OrchestrationModel):
    """Semantic match judgments for every objectively eligible candidate."""

    assessments: tuple[OfferMatchAssessment, ...]


class OfferDisplayParametersOutput(OrchestrationModel):
    """Four presentation-ready facts explaining the selected product match."""

    parameters: tuple[DisplayParameter, ...] = Field(min_length=4, max_length=4)


class IntentInterpreter(Protocol):
    async def normalize(
        self,
        raw_request: str,
        reporter: ActivityReporter | None = None,
    ) -> NormalizedPurchaseIntent: ...


class OfferPlanner(Protocol):
    async def select(
        self,
        intent: NormalizedPurchaseIntent,
        reporter: ActivityReporter | None = None,
    ) -> OfferSelectionPlan: ...


class ActivityRunHooks(RunHooks[None]):
    """Persist safe model and tool lifecycle signals without prompts or outputs."""

    def __init__(self, reporter: ActivityReporter, phase: ActivityPhase) -> None:
        self.reporter = reporter
        self.phase = phase

    async def on_llm_start(
        self,
        context: RunContextWrapper[None],
        agent: Agent[None],
        system_prompt: str | None,
        input_items: list[Any],
    ) -> None:
        self.reporter.record(
            kind="agent.llm.started",
            phase=self.phase,
            status=ActivityStatus.STARTED,
            title="Model reasoning started",
            message=f"{agent.name} is processing structured transaction context.",
        )

    async def on_llm_end(
        self,
        context: RunContextWrapper[None],
        agent: Agent[None],
        response: ModelResponse,
    ) -> None:
        self.reporter.record(
            kind="agent.llm.completed",
            phase=self.phase,
            status=ActivityStatus.COMPLETED,
            title="Model reasoning completed",
            message=f"{agent.name} returned a structured result.",
        )

    async def on_tool_start(
        self,
        context: RunContextWrapper[None],
        agent: Agent[None],
        tool: Tool,
    ) -> None:
        tool_name = str(getattr(tool, "name", tool.__class__.__name__))
        self.reporter.record(
            kind="agent.tool.started",
            phase=self.phase,
            status=ActivityStatus.STARTED,
            title=f"Calling {tool_name}",
            message="The agent is requesting authoritative merchant data.",
            authority="merchant",
            data={"tool_name": tool_name},
        )

    async def on_tool_end(
        self,
        context: RunContextWrapper[None],
        agent: Agent[None],
        tool: Tool,
        result: object,
    ) -> None:
        tool_name = str(getattr(tool, "name", tool.__class__.__name__))
        self.reporter.record(
            kind="agent.tool.completed",
            phase=self.phase,
            status=ActivityStatus.COMPLETED,
            title=f"Completed {tool_name}",
            message="The merchant returned authoritative structured data.",
            authority="merchant",
            data={"tool_name": tool_name},
        )


class DeterministicOfferPlanner:
    """Deterministic constraint evaluator over a merchant gateway."""

    def __init__(self, merchant: MerchantGateway) -> None:
        self.merchant = merchant

    async def select(
        self,
        intent: NormalizedPurchaseIntent,
        reporter: ActivityReporter | None = None,
    ) -> OfferSelectionPlan:
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
        offer: Offer,
        intent: NormalizedPurchaseIntent,
        *,
        check_semantic_attributes: bool = True,
    ) -> tuple[list[str], str | None, int]:
        reasons: list[str] = []
        if offer.available_quantity < intent.quantity:
            reasons.append("Insufficient stock.")
        if check_semantic_attributes:
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

    async def normalize(
        self,
        raw_request: str,
        reporter: ActivityReporter | None = None,
    ) -> NormalizedPurchaseIntent:
        hooks = ActivityRunHooks(reporter, ActivityPhase.INTENT) if reporter else None
        agent_request = (
            f"Current date: {self.today.isoformat()}\nPurchase request: {raw_request}"
        )
        result = await Runner.run(
            self.agent,
            agent_request,
            max_turns=2,
            hooks=hooks,
            run_config=RunConfig(
                workflow_name="commerce-intent-normalization",
                trace_include_sensitive_data=False,
            ),
        )
        output = result.final_output
        if not isinstance(output, PurchaseIntentOutput):
            raise RuntimeError("Intent agent returned an unexpected output type")
        _log_agent_exchange(self.agent.name, agent_request, output)
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
    """Semantic offer comparison over broad merchant candidates."""

    def __init__(
        self,
        model: str,
        merchant: MerchantGateway,
        reasoning_effort: ReasoningEffort,
    ) -> None:
        self.model = model
        self.merchant = merchant
        self.reasoning_effort = reasoning_effort

    async def select(
        self,
        intent: NormalizedPurchaseIntent,
        reporter: ActivityReporter | None = None,
    ) -> OfferSelectionPlan:
        offers = await self.merchant.search_offers(
            SearchOffersRequest(currency=intent.currency, quantity=intent.quantity)
        )
        eligible: list[tuple[Offer, str, int]] = []
        rejected: list[RejectedOffer] = []
        for offer in offers:
            reasons, delivery_id, total = DeterministicOfferPlanner._evaluate(
                offer,
                intent,
                check_semantic_attributes=False,
            )
            if reasons or delivery_id is None:
                rejected.append(RejectedOffer(offer_id=offer.offer_id, reasons=tuple(reasons)))
            else:
                eligible.append((offer, delivery_id, total))
        if not eligible:
            return OfferSelectionPlan(
                selected_offer_id=None,
                confidence=1,
                selection_reason="No merchant offer satisfies the objective purchase constraints.",
                rejected_offers=tuple(rejected),
            )

        agent = Agent(
            name="Commerce semantic offer matcher",
            model=self.model,
            model_settings=ModelSettings(
                reasoning=Reasoning(effort=self.reasoning_effort),
                verbosity="low",
            ),
            instructions=(
                "Compare the requested product meaning with every supplied candidate. Treat "
                "different natural-language names and machine attribute keys as potentially "
                "expressing the same fact. Mark matches=true only when the candidate's name, "
                "description, category, variant, or structured attributes provide evidence for "
                "every semantic product requirement. Do not perform price, stock, delivery, or "
                "return-policy arithmetic; candidates already satisfy those objective checks. "
                "Return exactly one assessment for every supplied offer_id and never invent IDs."
            ),
            output_type=OfferComparisonOutput,
        )
        agent_request = json.dumps(
            {
                "intent": intent.model_dump(mode="json"),
                "candidates": [offer.model_dump(mode="json") for offer, _, _ in eligible],
            },
            ensure_ascii=False,
            indent=2,
        )
        result = await Runner.run(
            agent,
            agent_request,
            max_turns=2,
            hooks=(ActivityRunHooks(reporter, ActivityPhase.DISCOVERY) if reporter else None),
            run_config=RunConfig(
                workflow_name="commerce-semantic-offer-matching",
                trace_include_sensitive_data=False,
            ),
        )
        output = result.final_output
        if not isinstance(output, OfferComparisonOutput):
            raise RuntimeError("Offer matcher returned an unexpected output type")
        _log_agent_exchange(agent.name, agent_request, output)
        selection = self._build_selection(intent, eligible, rejected, output)
        if selection.selected_offer_id is None:
            return selection
        selected_offer, selected_delivery_id, delivered_total_minor = next(
            candidate
            for candidate in eligible
            if candidate[0].offer_id == selection.selected_offer_id
        )
        display_parameters = await self._create_display_parameters(
            intent,
            selected_offer,
            selected_delivery_id,
            delivered_total_minor,
            reporter,
        )
        return selection.model_copy(update={"display_parameters": display_parameters})

    async def _create_display_parameters(
        self,
        intent: NormalizedPurchaseIntent,
        selected_offer: Offer,
        selected_delivery_id: str,
        delivered_total_minor: int,
        reporter: ActivityReporter | None,
    ) -> tuple[DisplayParameter, ...]:
        agent = Agent(
            name="Selected offer parameter presenter",
            model=self.model,
            model_settings=ModelSettings(
                reasoning=Reasoning(effort=self.reasoning_effort),
                verbosity="low",
            ),
            instructions=(
                "Choose exactly four parameters that best explain why the selected offer fits "
                "the user's purchase intent. Return concise, presentation-ready label and value "
                "strings. Prioritize the user's hard requirements and the most decision-relevant "
                "product facts. Ground every value in the supplied intent or authoritative offer; "
                "do not invent facts, IDs, scores, or technical attribute names. Format money, "
                "dates, units, and boolean facts for a human reader."
            ),
            output_type=OfferDisplayParametersOutput,
        )
        agent_request = json.dumps(
            {
                "intent": intent.model_dump(mode="json"),
                "selected_offer": selected_offer.model_dump(mode="json"),
                "selected_delivery_option": next(
                    option.model_dump(mode="json")
                    for option in selected_offer.delivery_options
                    if option.delivery_option_id == selected_delivery_id
                ),
                "delivered_total_minor": delivered_total_minor,
                "currency": selected_offer.unit_price.currency,
            },
            ensure_ascii=False,
            indent=2,
        )
        result = await Runner.run(
            agent,
            agent_request,
            max_turns=2,
            hooks=(ActivityRunHooks(reporter, ActivityPhase.DISCOVERY) if reporter else None),
            run_config=RunConfig(
                workflow_name="commerce-selected-offer-parameters",
                trace_include_sensitive_data=False,
            ),
        )
        output = result.final_output
        if not isinstance(output, OfferDisplayParametersOutput):
            raise RuntimeError("Offer parameter presenter returned an unexpected output type")
        _log_agent_exchange(agent.name, agent_request, output)
        return output.parameters

    @staticmethod
    def _build_selection(
        intent: NormalizedPurchaseIntent,
        eligible: list[tuple[Offer, str, int]],
        rejected: list[RejectedOffer],
        output: OfferComparisonOutput,
    ) -> OfferSelectionPlan:
        candidates = {
            offer.offer_id: (offer, delivery_id, total)
            for offer, delivery_id, total in eligible
        }
        assessment_ids = [assessment.offer_id for assessment in output.assessments]
        duplicate_ids = len(assessment_ids) != len(set(assessment_ids))
        missing_or_unknown_ids = set(assessment_ids) != set(candidates)
        if duplicate_ids or missing_or_unknown_ids:
            raise RuntimeError("Offer matcher must assess every candidate exactly once")
        matches = [assessment for assessment in output.assessments if assessment.matches]
        semantic_rejections = [
            RejectedOffer(offer_id=item.offer_id, reasons=(item.reason,))
            for item in output.assessments
            if not item.matches
        ]
        all_rejected = tuple([*rejected, *semantic_rejections])
        if not matches:
            return OfferSelectionPlan(
                selected_offer_id=None,
                confidence=max((item.confidence for item in output.assessments), default=1),
                selection_reason="The agent found no semantic product match among eligible offers.",
                rejected_offers=all_rejected,
            )
        selected_assessment = min(
            matches,
            key=lambda item: (-item.confidence, candidates[item.offer_id][2]),
        )
        selected, delivery_id, _ = candidates[selected_assessment.offer_id]
        constraints = ["semantic product match", "stock", "budget"]
        if intent.latest_delivery_date is not None:
            constraints.append("delivery")
        if intent.minimum_return_window_days is not None:
            constraints.append("returns")
        return OfferSelectionPlan(
            selected_offer_id=selected.offer_id,
            selected_offer_version=selected.version,
            delivery_option_id=delivery_id,
            confidence=selected_assessment.confidence,
            selection_reason=selected_assessment.reason,
            satisfied_constraints=tuple(constraints),
            rejected_offers=all_rejected,
        )
