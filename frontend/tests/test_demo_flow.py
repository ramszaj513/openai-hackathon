from datetime import date

from frontend.demo_flow import (
    canonical_constraints,
    evaluate_offer,
    format_money,
    proposal_binding,
    select_offer,
)


def offer(*, offer_id: str, price: int, mac: bool, delivery: str, returns: int, size: int):
    return {
        "offer_id": offer_id,
        "unit_price": {"amount_minor": price, "currency": "PLN"},
        "product": {"attributes": {"mac_compatible": mac, "size_inches": size}},
        "delivery_options": [{"estimated_delivery_date": delivery, "price_minor": 0}],
        "return_policy": {"returnable": True, "window_days": returns},
    }


def test_offer_evaluation_and_selection_respect_hard_constraints() -> None:
    constraints = canonical_constraints(date(2026, 7, 11))
    valid = offer(
        offer_id="valid", price=114_900, mac=True, delivery="2026-07-12", returns=30, size=27
    )
    late = offer(
        offer_id="late", price=84_900, mac=True, delivery="2026-07-15", returns=30, size=24
    )
    incompatible = offer(
        offer_id="wrong", price=99_900, mac=False, delivery="2026-07-12", returns=30, size=32
    )

    assert evaluate_offer(valid, constraints) == []
    assert evaluate_offer(late, constraints) == ["delivery is too late"]
    assert evaluate_offer(incompatible, constraints) == ["not Mac-compatible"]
    assert select_offer([late, incompatible, valid], constraints)["offer_id"] == "valid"


def test_proposal_binding_changes_with_material_checkout_change() -> None:
    checkout = {
        "checkout_id": "chk_1",
        "version": 1,
        "merchant_id": "merchant_1",
        "lines": [{"offer_id": "offer_1", "quantity": 1}],
        "delivery_option": {"delivery_option_id": "next-day"},
        "price": {"total_minor": 100_00, "currency": "PLN"},
        "return_policy": {"window_days": 30},
        "expires_at": "2026-07-11T12:00:00Z",
    }

    changed = {**checkout, "version": 2, "price": {"total_minor": 110_00, "currency": "PLN"}}
    assert proposal_binding(checkout) != proposal_binding(changed)


def test_money_is_formatted_from_minor_units() -> None:
    assert format_money(114_900, "PLN") == "1 149.00 PLN"

