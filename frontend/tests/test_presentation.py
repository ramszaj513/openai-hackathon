from frontend.presentation import format_money


def test_money_is_formatted_from_minor_units() -> None:
    assert format_money(114_900, "PLN") == "1 149.00 PLN"
