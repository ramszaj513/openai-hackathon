"""Agent transaction REST routes for the Streamlit integration owner."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import StreamingResponse

from agent_commerce.orchestration.activity import TransactionActivity
from agent_commerce.orchestration.models import (
    AgentTransaction,
    ApproveTransactionRequest,
    CancelTransactionRequest,
    ReturnTransactionRequest,
    StartPurchaseRequest,
    TransactionAccepted,
)
from agent_commerce.orchestration.service import CommerceOrchestrator


def create_orchestration_router(orchestrator: CommerceOrchestrator) -> APIRouter:
    router = APIRouter(prefix="/api/agent", tags=["agent"])

    def get_orchestrator() -> CommerceOrchestrator:
        return orchestrator

    Orchestrator = Depends(get_orchestrator)

    @router.post("/transactions", response_model=TransactionAccepted, status_code=202)
    async def start_transaction(
        request: StartPurchaseRequest,
        background_tasks: BackgroundTasks,
        agent: CommerceOrchestrator = Orchestrator,
    ) -> TransactionAccepted:
        submission = agent.begin(request)
        transaction_id = submission.transaction.transaction_id
        if submission.should_process:
            background_tasks.add_task(
                agent.process,
                request,
                transaction_id,
                submission.fingerprint,
            )
        base = f"/api/agent/transactions/{transaction_id}"
        return TransactionAccepted(
            transaction=submission.transaction,
            status_url=base,
            activity_url=f"{base}/activity",
            stream_url=f"{base}/stream",
        )

    @router.get("/transactions/{transaction_id}", response_model=AgentTransaction)
    def get_transaction(
        transaction_id: str,
        agent: CommerceOrchestrator = Orchestrator,
    ) -> AgentTransaction:
        return agent.get(transaction_id)

    @router.get(
        "/transactions/{transaction_id}/activity",
        response_model=list[TransactionActivity],
    )
    def list_transaction_activity(
        transaction_id: str,
        after_sequence: int = Query(default=0, ge=0),
        agent: CommerceOrchestrator = Orchestrator,
    ) -> list[TransactionActivity]:
        return agent.list_activities(transaction_id, after_sequence=after_sequence)

    @router.get("/transactions/{transaction_id}/stream")
    async def stream_transaction_activity(
        transaction_id: str,
        request: Request,
        after_sequence: int = Query(default=0, ge=0),
        once: bool = False,
        agent: CommerceOrchestrator = Orchestrator,
    ) -> StreamingResponse:
        agent.get(transaction_id)
        last_event_id = request.headers.get("last-event-id")
        cursor = max(after_sequence, _sequence_from_event_id(last_event_id))

        async def events() -> AsyncIterator[str]:
            nonlocal cursor
            loop = asyncio.get_running_loop()
            next_heartbeat = loop.time() + 10
            while True:
                batch = agent.list_activities(transaction_id, after_sequence=cursor)
                for activity in batch:
                    cursor = activity.sequence
                    payload = json.dumps(activity.model_dump(mode="json"), separators=(",", ":"))
                    yield (
                        f"id: {activity.event_id}\nevent: transaction.activity\ndata: {payload}\n\n"
                    )
                if once:
                    return
                if await request.is_disconnected():
                    return
                if not batch and loop.time() >= next_heartbeat:
                    yield ": heartbeat\n\n"
                    next_heartbeat = loop.time() + 10
                await asyncio.sleep(0.5)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post(
        "/transactions/{transaction_id}/approve",
        response_model=AgentTransaction,
    )
    async def approve_transaction(
        transaction_id: str,
        request: ApproveTransactionRequest,
        agent: CommerceOrchestrator = Orchestrator,
    ) -> AgentTransaction:
        _validate_transaction_path(transaction_id, request.transaction_id)
        return await agent.approve(request)

    @router.post(
        "/transactions/{transaction_id}/resume",
        response_model=AgentTransaction,
    )
    async def resume_transaction(
        transaction_id: str,
        agent: CommerceOrchestrator = Orchestrator,
    ) -> AgentTransaction:
        return await agent.resume_from_events(transaction_id)

    @router.post(
        "/transactions/{transaction_id}/cancel",
        response_model=AgentTransaction,
    )
    async def cancel_transaction(
        transaction_id: str,
        request: CancelTransactionRequest,
        agent: CommerceOrchestrator = Orchestrator,
    ) -> AgentTransaction:
        _validate_transaction_path(transaction_id, request.transaction_id)
        return await agent.cancel(request)

    @router.post(
        "/transactions/{transaction_id}/return",
        response_model=AgentTransaction,
    )
    async def return_transaction(
        transaction_id: str,
        request: ReturnTransactionRequest,
        agent: CommerceOrchestrator = Orchestrator,
    ) -> AgentTransaction:
        _validate_transaction_path(transaction_id, request.transaction_id)
        return await agent.return_order(request)

    return router


def _validate_transaction_path(path_id: str, request_id: str) -> None:
    if path_id != request_id:
        from agent_commerce.commerce.errors import validation_error

        raise validation_error("Path transaction_id does not match request transaction_id")


def _sequence_from_event_id(event_id: str | None) -> int:
    if not event_id:
        return 0
    try:
        return int(event_id.rsplit(":", maxsplit=1)[-1])
    except ValueError:
        return 0
