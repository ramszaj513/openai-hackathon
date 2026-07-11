"""Presentation-only constants and formatting helpers."""

CANONICAL_REQUEST = (
    "Buy a Mac-compatible monitor for no more than 1,200 PLN, deliverable tomorrow, "
    "with at least a 30-day return window. Buy it if you are confident."
)


def format_money(amount_minor: int, currency: str) -> str:
    return f"{amount_minor / 100:,.2f} {currency}".replace(",", " ")

