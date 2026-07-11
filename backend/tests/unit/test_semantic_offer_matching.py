from datetime import datetime

from agent_commerce.commerce.models import SearchOffersRequest
from agent_commerce.commerce.service import CommerceService
from agent_commerce.orchestration.brain import (
    DeterministicOfferPlanner,
    OfferComparisonOutput,
    OfferMatchAssessment,
    OpenAIOfferPlanner,
)
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
