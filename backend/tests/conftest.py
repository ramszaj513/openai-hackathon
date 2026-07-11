from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest
from agent_commerce.audit import AuditLedger
from agent_commerce.commerce.repository import InMemoryCommerceRepository
from agent_commerce.commerce.seed import build_seed_offers
from agent_commerce.commerce.service import CommerceService
from agent_commerce.payments import PaymentService
from agent_commerce.payments.repository import InMemoryPaymentRepository
from agent_commerce.trust import TrustService
from agent_commerce.trust.repository import InMemoryTrustRepository


@dataclass
class MutableClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **delta: int) -> None:
        self.current += timedelta(**delta)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 7, 11, 10, 0, tzinfo=UTC)


@pytest.fixture
def clock(now: datetime) -> MutableClock:
    return MutableClock(now)


@pytest.fixture
def service(clock: MutableClock, now: datetime) -> CommerceService:
    repository = InMemoryCommerceRepository()
    for offer in build_seed_offers(now):
        repository.save_offer(offer)
    ids = count(1)
    return CommerceService(
        repository,
        clock=clock,
        id_factory=lambda: f"{next(ids):08d}",
    )


@pytest.fixture
def audit(clock: MutableClock) -> AuditLedger:
    ids = count(1)
    return AuditLedger(clock=clock, id_factory=lambda: f"{next(ids):08d}")


@pytest.fixture
def trust(clock: MutableClock, audit: AuditLedger) -> TrustService:
    ids = count(1)
    return TrustService(
        InMemoryTrustRepository(),
        audit,
        clock=clock,
        id_factory=lambda: f"{next(ids):08d}",
    )


@pytest.fixture
def payments(clock: MutableClock, audit: AuditLedger, trust: TrustService) -> PaymentService:
    ids = count(1)
    return PaymentService(
        trust,
        InMemoryPaymentRepository(),
        audit,
        clock=clock,
        id_factory=lambda: f"{next(ids):08d}",
    )
