from __future__ import annotations

from collections import Counter
from datetime import datetime

from agent_commerce.commerce.models import SearchOffersRequest
from agent_commerce.commerce.seed import build_seed_offers
from agent_commerce.commerce.service import CommerceService


def test_seed_catalog_has_varied_multi_category_inventory(now: datetime) -> None:
    offers = build_seed_offers(now)
    category_counts = Counter(offer.product.category for offer in offers)

    assert len(offers) == 24
    assert len({offer.offer_id for offer in offers}) == 24
    assert len({offer.product.product_id for offer in offers}) == 24
    assert category_counts == {
        "monitor": 4,
        "laptop": 6,
        "phone": 6,
        "tablet": 3,
        "headphones": 2,
        "keyboard": 1,
        "smartwatch": 1,
        "dock": 1,
    }
    assert {offer.return_policy.window_days for offer in offers} >= {14, 30, 60}
    assert all(offer.delivery_options for offer in offers)


def test_expanded_catalog_supports_category_query_and_attribute_search(
    service: CommerceService,
) -> None:
    phones = service.search_offers(SearchOffersRequest(category="phone"))
    gaming_laptops = service.search_offers(
        SearchOffersRequest(query="gaming laptop", category="laptop")
    )
    high_memory_laptops = service.search_offers(
        SearchOffersRequest(category="laptop", required_attributes={"ram_gb": 32})
    )
    noise_cancelling_headphones = service.search_offers(
        SearchOffersRequest(query="wireless noise cancelling headphones")
    )

    assert len(phones) == 6
    assert [offer.offer_id for offer in gaming_laptops] == ["offer-laptop-gamecore-16"]
    assert [offer.offer_id for offer in high_memory_laptops] == [
        "offer-laptop-forge-pro-14",
        "offer-laptop-gamecore-16",
        "offer-laptop-creator-16",
    ]
    assert [offer.offer_id for offer in noise_cancelling_headphones] == [
        "offer-headphones-quiet-pro"
    ]
