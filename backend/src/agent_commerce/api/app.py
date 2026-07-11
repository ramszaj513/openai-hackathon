"""FastAPI composition root for commerce REST and MCP transports."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_commerce.api.orchestration_routes import create_orchestration_router
from agent_commerce.api.payment_routes import create_payment_router
from agent_commerce.api.routes import create_commerce_router
from agent_commerce.api.transcription_routes import create_transcription_router
from agent_commerce.api.trust_routes import create_trust_router
from agent_commerce.audit import AuditLedger
from agent_commerce.commerce.errors import CommerceError
from agent_commerce.commerce.service import CommerceService
from agent_commerce.mcp_server import create_commerce_mcp
from agent_commerce.orchestration.factory import create_default_orchestrator
from agent_commerce.orchestration.service import CommerceOrchestrator
from agent_commerce.payments import PaymentService
from agent_commerce.transcription import RealtimeTranscriptionService
from agent_commerce.transcription.service import TranscriptionDelay
from agent_commerce.trust import TrustService


def create_app(
    service: CommerceService | None = None,
    trust_service: TrustService | None = None,
    payment_service: PaymentService | None = None,
    orchestrator: CommerceOrchestrator | None = None,
    transcription_service: RealtimeTranscriptionService | None = None,
) -> FastAPI:
    commerce = service or CommerceService.with_seed_data()
    if payment_service is not None:
        payments = payment_service
        trust = trust_service or payments.trust
        audit = payments.audit
    elif trust_service is not None:
        trust = trust_service
        audit = trust.audit
        payments = PaymentService(trust, audit=audit)
    else:
        audit = AuditLedger()
        trust = TrustService(audit=audit)
        payments = PaymentService(trust, audit=audit)
    _wire_checkout_approval_invalidation(commerce, trust)
    agent_orchestrator = orchestrator or create_default_orchestrator(
        commerce,
        trust,
        payments,
    )
    mcp = create_commerce_mcp(commerce)
    transcription = transcription_service or RealtimeTranscriptionService(
        os.getenv("OPENAI_API_KEY"),
        model=os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-realtime-whisper"),
        language=os.getenv("OPENAI_TRANSCRIPTION_LANGUAGE", "pl") or None,
        delay=_transcription_delay_from_environment(),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = FastAPI(
        title="Agent Commerce Gateway",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.exception_handler(CommerceError)
    async def handle_commerce_error(_: Request, exc: CommerceError) -> JSONResponse:
        status_by_code = {
            "NOT_FOUND": 404,
            "VALIDATION_ERROR": 422,
            "STALE_VERSION": 409,
            "CONFLICT": 409,
            "IDEMPOTENCY_CONFLICT": 409,
            "OUT_OF_STOCK": 409,
            "PRICE_CHANGED": 409,
            "EXPIRED": 410,
            "APPROVAL_REQUIRED": 403,
            "APPROVAL_INVALID": 403,
            "PAYMENT_DECLINED": 402,
            "NOT_CANCELLABLE": 409,
            "NOT_RETURNABLE": 409,
            "RECOVERY_REQUIRED": 503,
        }
        return JSONResponse(
            status_code=status_by_code.get(exc.code, 400),
            content=exc.as_dict(),
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(create_commerce_router(commerce))
    app.include_router(create_trust_router(trust, commerce))
    app.include_router(create_payment_router(payments))
    app.include_router(create_orchestration_router(agent_orchestrator))
    app.include_router(create_transcription_router(transcription))
    app.mount("/", mcp.streamable_http_app())
    app.state.commerce_service = commerce
    app.state.commerce_mcp = mcp
    app.state.trust_service = trust
    app.state.payment_service = payments
    app.state.audit_ledger = audit
    app.state.commerce_orchestrator = agent_orchestrator
    app.state.transcription_service = transcription
    return app


def _wire_checkout_approval_invalidation(commerce: CommerceService, trust: TrustService) -> None:
    def handle_event(event: Any) -> None:
        if event.event_type not in {
            "checkout.updated",
            "checkout.expired",
            "checkout.cancelled",
        }:
            return
        if event.subject_version is None:
            return
        trust.invalidate_checkout(event.subject_id, event.subject_version)

    commerce.add_event_handler(handle_event)


def _transcription_delay_from_environment() -> TranscriptionDelay:
    delay = os.getenv("OPENAI_TRANSCRIPTION_DELAY", "low").lower()
    allowed = {"minimal", "low", "medium", "high", "xhigh"}
    if delay not in allowed:
        expected = ", ".join(sorted(allowed))
        raise RuntimeError(f"OPENAI_TRANSCRIPTION_DELAY must be one of: {expected}")
    return cast(TranscriptionDelay, delay)
