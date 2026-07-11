"""Trust and consent REST routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_commerce.commerce.models import ApprovalEvidence
from agent_commerce.commerce.service import CommerceService
from agent_commerce.trust.models import (
    ApprovalRecord,
    CheckoutProposal,
    CreateCheckoutProposalRequest,
    CreateSpendingMandateRequest,
    EvaluateProposalRequest,
    ExplicitApprovalRequest,
    PolicyDecision,
    RejectProposalRequest,
    RevokeMandateRequest,
    SpendingMandate,
)
from agent_commerce.trust.service import TrustService


def create_trust_router(
    trust_service: TrustService, commerce_service: CommerceService
) -> APIRouter:
    router = APIRouter(prefix="/api/trust", tags=["trust"])

    def get_trust() -> TrustService:
        return trust_service

    def get_commerce() -> CommerceService:
        return commerce_service

    Trust = Depends(get_trust)
    Commerce = Depends(get_commerce)

    @router.post("/mandates", response_model=SpendingMandate, status_code=201)
    def create_mandate(
        request: CreateSpendingMandateRequest, trust: TrustService = Trust
    ) -> SpendingMandate:
        return trust.create_mandate(request)

    @router.get("/mandates/{mandate_id}", response_model=SpendingMandate)
    def get_mandate(mandate_id: str, trust: TrustService = Trust) -> SpendingMandate:
        return trust.get_mandate(mandate_id)

    @router.post("/mandates/{mandate_id}/revoke", response_model=SpendingMandate)
    def revoke_mandate(
        mandate_id: str,
        request: RevokeMandateRequest,
        trust: TrustService = Trust,
    ) -> SpendingMandate:
        if request.mandate_id != mandate_id:
            from agent_commerce.commerce.errors import validation_error

            raise validation_error("Path mandate_id does not match request mandate_id")
        return trust.revoke_mandate(request)

    @router.post("/proposals", response_model=CheckoutProposal, status_code=201)
    def create_proposal(
        request: CreateCheckoutProposalRequest,
        trust: TrustService = Trust,
        commerce: CommerceService = Commerce,
    ) -> CheckoutProposal:
        return trust.create_proposal(commerce.get_checkout(request.checkout_id), request)

    @router.get("/proposals/{proposal_id}", response_model=CheckoutProposal)
    def get_proposal(proposal_id: str, trust: TrustService = Trust) -> CheckoutProposal:
        return trust.get_proposal(proposal_id)

    @router.post("/proposals/{proposal_id}/evaluate", response_model=PolicyDecision)
    def evaluate_proposal(
        proposal_id: str,
        request: EvaluateProposalRequest,
        trust: TrustService = Trust,
    ) -> PolicyDecision:
        if request.proposal_id != proposal_id:
            from agent_commerce.commerce.errors import validation_error

            raise validation_error("Path proposal_id does not match request proposal_id")
        return trust.evaluate_proposal(request)

    @router.post("/proposals/{proposal_id}/approve", response_model=ApprovalRecord)
    def approve_proposal(
        proposal_id: str,
        request: ExplicitApprovalRequest,
        trust: TrustService = Trust,
    ) -> ApprovalRecord:
        if request.proposal_id != proposal_id:
            from agent_commerce.commerce.errors import validation_error

            raise validation_error("Path proposal_id does not match request proposal_id")
        return trust.approve_proposal(request)

    @router.post("/proposals/{proposal_id}/reject", response_model=CheckoutProposal)
    def reject_proposal(
        proposal_id: str,
        request: RejectProposalRequest,
        trust: TrustService = Trust,
    ) -> CheckoutProposal:
        if request.proposal_id != proposal_id:
            from agent_commerce.commerce.errors import validation_error

            raise validation_error("Path proposal_id does not match request proposal_id")
        return trust.reject_proposal(request)

    @router.get("/approvals/{approval_id}", response_model=ApprovalRecord)
    def get_approval(approval_id: str, trust: TrustService = Trust) -> ApprovalRecord:
        return trust.get_approval(approval_id)

    @router.get("/approvals/{approval_id}/evidence", response_model=ApprovalEvidence)
    def get_approval_evidence(
        approval_id: str, trust: TrustService = Trust
    ) -> ApprovalEvidence:
        return trust.get_approval_evidence(approval_id)

    return router

