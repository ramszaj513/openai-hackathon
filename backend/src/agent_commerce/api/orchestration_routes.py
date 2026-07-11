"""Agent transaction REST routes for the Streamlit integration owner."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_commerce.orchestration.models import (
    AgentTransaction,
    ApproveTransactionRequest,
    CancelTransactionRequest,
    ReturnTransactionRequest,
    StartPurchaseRequest,
)
from agent_commerce.orchestration.service import CommerceOrchestrator


def create_orchestration_router(orchestrator: CommerceOrchestrator) -> APIRouter:
    router = APIRouter(prefix="/api/agent", tags=["agent"])

    def get_orchestrator() -> CommerceOrchestrator:
        return orchestrator

    Orchestrator = Depends(get_orchestrator)

    @router.post("/transactions", response_model=AgentTransaction, status_code=201)
    async def start_transaction(
        request: StartPurchaseRequest,
        agent: CommerceOrchestrator = Orchestrator,
    ) -> AgentTransaction:
        return await agent.start(request)

    @router.get("/transactions/{transaction_id}", response_model=AgentTransaction)
    def get_transaction(
        transaction_id: str,
        agent: CommerceOrchestrator = Orchestrator,
    ) -> AgentTransaction:
        return agent.get(transaction_id)

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
