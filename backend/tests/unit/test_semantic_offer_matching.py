from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agent_commerce.commerce.models import SearchOffersRequest
from agent_commerce.commerce.service import CommerceService
from agent_commerce.orchestration import brain
from agent_commerce.orchestration.brain import (
    DeterministicOfferPlanner,
    OfferComparisonOutput,
    OfferDisplayParametersOutput,
    OfferMatchAssessment,
    OpenAIOfferPlanner,
)
from agent_commerce.orchestration.merchant_gateway import DirectMerchantGateway
from agent_commerce.orchestration.models import DisplayParameter
from conftest import canonical_intent


def test_agent_match_selects_offer_despite_different_attribute_name(
    service: CommerceService,
    now: datetime,
) -> None:
    intent = canonical_intent(now).model_copy(
        update={"required_attributes": {"Mac compatibility": True}}
    )
    offers = service.search_offers(SearchOffersRequest(currency="PLN", quantity=1))
    eligible = []
    for offer in offers:
        reasons, delivery_id, total = DeterministicOfferPlanner._evaluate(
            offer,
            intent,
            check_semantic_attributes=False,
        )
        if not reasons and delivery_id is not None:
            eligible.append((offer, delivery_id, total))

    output = OfferComparisonOutput(
        assessments=tuple(
            OfferMatchAssessment(
                offer_id=offer.offer_id,
                matches=offer.offer_id == "offer-studio-27-usbc",
                confidence=0.99,
                reason=(
                    "The description explicitly confirms macOS compatibility."
                    if offer.offer_id == "offer-studio-27-usbc"
                    else "The product explicitly lacks supported Mac USB-C input."
                ),
            )
            for offer, _, _ in eligible
        )
    )

    selection = OpenAIOfferPlanner._build_selection(intent, eligible, [], output)

    assert selection.selected_offer_id == "offer-studio-27-usbc"
    assert selection.delivery_option_id == "delivery-next-day"
    assert selection.confidence == 0.99
    assert "semantic product match" in selection.satisfied_constraints


@pytest.mark.asyncio
async def test_successful_match_runs_agent_again_for_four_display_parameters(
    service: CommerceService,
    now: datetime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent = canonical_intent(now).model_copy(
        update={"required_attributes": {"Mac compatibility": True}}
    )
    offers = service.search_offers(SearchOffersRequest(currency="PLN", quantity=1))
    eligible_offer_ids = []
    for offer in offers:
        reasons, delivery_id, _ = DeterministicOfferPlanner._evaluate(
            offer,
            intent,
            check_semantic_attributes=False,
        )
        if not reasons and delivery_id is not None:
            eligible_offer_ids.append(offer.offer_id)
    comparison = OfferComparisonOutput(
        assessments=tuple(
            OfferMatchAssessment(
                offer_id=offer_id,
                matches=offer_id == "offer-studio-27-usbc",
                confidence=1,
                reason=(
                    "Compatible with macOS."
                    if offer_id == "offer-studio-27-usbc"
                    else "Not the requested product match."
                ),
            )
            for offer_id in eligible_offer_ids
        )
    )
    presentation = OfferDisplayParametersOutput(
        parameters=(
            DisplayParameter(label="Compatibility", value="Mac and macOS"),
            DisplayParameter(label="Price", value="PLN 1,149.00"),
            DisplayParameter(label="Delivery", value="Tomorrow"),
            DisplayParameter(label="Returns", value="30 days"),
        )
    )
    run = AsyncMock(
        side_effect=(
            SimpleNamespace(final_output=comparison),
            SimpleNamespace(final_output=presentation),
        )
    )
    monkeypatch.setattr(brain.Runner, "run", run)
    planner = OpenAIOfferPlanner("test-model", DirectMerchantGateway(service), "low")

    selection = await planner.select(intent)

    assert run.await_count == 2
    assert selection.selected_offer_id == "offer-studio-27-usbc"
    assert selection.display_parameters == presentation.parameters
