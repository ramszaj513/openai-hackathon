"""Deterministic merchant seed data for the canonical monitor scenario."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from agent_commerce.commerce.models import (
    DeliveryOption,
    Money,
    Offer,
    Product,
    ReturnPolicy,
)

MERCHANT_ID = "merchant-demo-electronics"


def build_seed_offers(now: datetime | None = None) -> list[Offer]:
    current = now or datetime.now(UTC)
    today = current.date()

    tomorrow_free = DeliveryOption(
        delivery_option_id="delivery-next-day",
        label="Next-day delivery",
        price_minor=0,
        estimated_delivery_date=today + timedelta(days=1),
    )
    tomorrow_paid = DeliveryOption(
        delivery_option_id="delivery-next-day",
        label="Next-day courier",
        price_minor=2999,
        estimated_delivery_date=today + timedelta(days=1),
    )
    standard = DeliveryOption(
        delivery_option_id="delivery-standard",
        label="Standard delivery",
        price_minor=0,
        estimated_delivery_date=today + timedelta(days=4),
    )

    return [
        Offer(
            offer_id="offer-studio-27-usbc",
            merchant_id=MERCHANT_ID,
            product=Product(
                product_id="monitor-studio-27",
                name="StudioView 27 USB-C",
                category="monitor",
                brand="StudioView",
                description="27-inch USB-C monitor with 90W charging and macOS compatibility.",
                attributes={
                    "mac_compatible": True,
                    "usb_c": True,
                    "power_delivery_watts": 90,
                    "size_inches": 27,
                },
            ),
            variant="27-inch / graphite",
            unit_price=Money(amount_minor=114900, currency="PLN"),
            available_quantity=5,
            delivery_options=(tomorrow_free, standard),
            return_policy=ReturnPolicy(
                returnable=True,
                window_days=30,
                description="Free returns within 30 days.",
            ),
            version=1,
            expires_at=current + timedelta(hours=24),
        ),
        Offer(
            offer_id="offer-gamer-27-hdmi",
            merchant_id=MERCHANT_ID,
            product=Product(
                product_id="monitor-gamer-27",
                name="RapidFrame 27 Gaming",
                category="monitor",
                brand="RapidFrame",
                description="High-refresh HDMI gaming display without supported Mac USB-C input.",
                attributes={
                    "mac_compatible": False,
                    "usb_c": False,
                    "power_delivery_watts": 0,
                    "size_inches": 27,
                },
            ),
            variant="27-inch / black",
            unit_price=Money(amount_minor=104900, currency="PLN"),
            available_quantity=8,
            delivery_options=(tomorrow_paid, standard),
            return_policy=ReturnPolicy(
                returnable=True,
                window_days=30,
                description="Returns accepted within 30 days.",
            ),
            version=1,
            expires_at=current + timedelta(hours=24),
        ),
        Offer(
            offer_id="offer-value-24-usbc",
            merchant_id=MERCHANT_ID,
            product=Product(
                product_id="monitor-value-24",
                name="Everyday 24 USB-C",
                category="monitor",
                brand="Everyday",
                description="Affordable Mac-compatible USB-C monitor with standard delivery.",
                attributes={
                    "mac_compatible": True,
                    "usb_c": True,
                    "power_delivery_watts": 65,
                    "size_inches": 24,
                },
            ),
            variant="24-inch / silver",
            unit_price=Money(amount_minor=84900, currency="PLN"),
            available_quantity=12,
            delivery_options=(standard,),
            return_policy=ReturnPolicy(
                returnable=True,
                window_days=30,
                description="Returns accepted within 30 days.",
            ),
            version=1,
            expires_at=current + timedelta(hours=24),
        ),
        Offer(
            offer_id="offer-pro-32-usbc",
            merchant_id=MERCHANT_ID,
            product=Product(
                product_id="monitor-pro-32",
                name="Creator Pro 32 USB-C",
                category="monitor",
                brand="Creator Pro",
                description="Premium 32-inch Mac-compatible creator display.",
                attributes={
                    "mac_compatible": True,
                    "usb_c": True,
                    "power_delivery_watts": 100,
                    "size_inches": 32,
                },
            ),
            variant="32-inch / black",
            unit_price=Money(amount_minor=139900, currency="PLN"),
            available_quantity=3,
            delivery_options=(tomorrow_free, standard),
            return_policy=ReturnPolicy(
                returnable=True,
                window_days=14,
                description="Returns accepted within 14 days.",
            ),
            version=1,
            expires_at=current + timedelta(hours=24),
        ),
    ]


def canonical_latest_delivery_date(today: date | None = None) -> date:
    return (today or date.today()) + timedelta(days=1)
