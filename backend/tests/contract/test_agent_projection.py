from agent_commerce.orchestration.models import DisplayParameter, OfferSelectionPlan


def test_selection_projection_exposes_agent_generated_display_parameters() -> None:
    selection = OfferSelectionPlan(
        selected_offer_id="offer-1",
        selected_offer_version=1,
        delivery_option_id="delivery-1",
        confidence=0.99,
        selection_reason="The offer matches the request.",
        display_parameters=(
            DisplayParameter(label="Compatibility", value="Mac and macOS"),
            DisplayParameter(label="Price", value="PLN 1,149.00"),
            DisplayParameter(label="Delivery", value="Tomorrow"),
            DisplayParameter(label="Returns", value="30 days"),
        ),
    )

    payload = selection.model_dump(mode="json")

    assert payload["display_parameters"] == [
        {"label": "Compatibility", "value": "Mac and macOS"},
        {"label": "Price", "value": "PLN 1,149.00"},
        {"label": "Delivery", "value": "Tomorrow"},
        {"label": "Returns", "value": "30 days"},
    ]
