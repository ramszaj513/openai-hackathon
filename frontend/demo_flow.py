"""Deterministic presentation helpers for gaps in orchestration and trust services."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

CANONICAL_REQUEST = (
    "Buy a Mac-compatible monitor for no more than 1,200 PLN, deliverable tomorrow, "
    "with at least a 30-day return window. Buy it if you are confident."
)


def canonical_constraints(today: date | None = None) -> dict[str, Any]:
    current = today or date.today()
    return {
        "category": "monitor",
        "max_unit_price_minor": 120_000,
        "currency": "PLN",
        "required_attributes": {"mac_compatible": True},
        "latest_delivery_date": (current + timedelta(days=1)).isoformat(),
        "minimum_return_window_days": 30,
        "quantity": 1,
    }


def evaluate_offer(offer: dict[str, Any], constraints: dict[str, Any]) -> list[str]:
    """Explain deterministic eligibility without treating UI state as authority."""
    failures: list[str] = []
    money = offer["unit_price"]
    if money["currency"] != constraints["currency"]:
        failures.append("wrong currency")
    if money["amount_minor"] > constraints["max_unit_price_minor"]:
        failures.append("over budget")
    attributes = offer["product"]["attributes"]
    for key, required in constraints["required_attributes"].items():
        if attributes.get(key) != required:
            failures.append("not Mac-compatible" if key == "mac_compatible" else f"missing {key}")
    latest = date.fromisoformat(constraints["latest_delivery_date"])
    if not any(
        date.fromisoformat(option["estimated_delivery_date"]) <= latest
        for option in offer["delivery_options"]
    ):
        failures.append("delivery is too late")
    policy = offer["return_policy"]
    if (
        not policy["returnable"]
        or policy["window_days"] < constraints["minimum_return_window_days"]
    ):
        failures.append("return window is too short")
    return failures


def select_offer(offers: list[dict[str, Any]], constraints: dict[str, Any]) -> dict[str, Any]:
    eligible = [offer for offer in offers if not evaluate_offer(offer, constraints)]
    if not eligible:
        raise ValueError("No offer satisfies every hard constraint")
    return max(
        eligible,
        key=lambda offer: (
            int(offer["product"]["attributes"].get("size_inches", 0)),
            -int(offer["unit_price"]["amount_minor"]),
        ),
    )


def select_delivery(offer: dict[str, Any], latest_delivery_date: str) -> dict[str, Any]:
    latest = date.fromisoformat(latest_delivery_date)
    eligible = [
        option
        for option in offer["delivery_options"]
        if date.fromisoformat(option["estimated_delivery_date"]) <= latest
    ]
    if not eligible:
        raise ValueError("No delivery option satisfies the deadline")
    return min(
        eligible,
        key=lambda option: (option["price_minor"], option["estimated_delivery_date"]),
    )


def proposal_binding(checkout: dict[str, Any]) -> str:
    snapshot = {
        "checkout_id": checkout["checkout_id"],
        "version": checkout["version"],
        "merchant_id": checkout["merchant_id"],
        "lines": checkout["lines"],
        "delivery_option": checkout["delivery_option"],
        "price": checkout["price"],
        "return_policy": checkout["return_policy"],
        "expires_at": checkout["expires_at"],
    }
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def demo_authority(checkout: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create safe, short-lived stand-ins until Piotr's trust service is integrated."""
    expires_at = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    shared = {
        "checkout_id": checkout["checkout_id"],
        "checkout_version": checkout["version"],
        "merchant_id": checkout["merchant_id"],
        "amount_minor": checkout["price"]["total_minor"],
        "currency": checkout["price"]["currency"],
        "expires_at": expires_at,
    }
    approval = {"approval_id": f"approval_demo_{uuid4().hex}", **shared}
    payment = {
        "payment_authorization_id": f"payauth_demo_{uuid4().hex}",
        **shared,
        "status": "AUTHORIZED",
    }
    return approval, payment


def format_money(amount_minor: int, currency: str) -> str:
    return f"{amount_minor / 100:,.2f} {currency}".replace(",", " ")
