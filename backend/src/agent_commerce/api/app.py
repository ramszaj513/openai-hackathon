"""FastAPI composition root for commerce REST and MCP transports."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_commerce.api.routes import create_commerce_router
from agent_commerce.commerce.errors import CommerceError
from agent_commerce.commerce.service import CommerceService
from agent_commerce.mcp_server import create_commerce_mcp


def create_app(service: CommerceService | None = None) -> FastAPI:
    commerce = service or CommerceService.with_seed_data()
    mcp = create_commerce_mcp(commerce)

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
    app.mount("/", mcp.streamable_http_app())
    app.state.commerce_service = commerce
    app.state.commerce_mcp = mcp
    return app

