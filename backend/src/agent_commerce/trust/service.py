"""Deterministic consent, spending-mandate, and approval service."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel

from agent_commerce.audit import AuditLedger
from agent_commerce.commerce.errors import CommerceError, conflict, not_found, validation_error
from agent_commerce.commerce.models import ApprovalEvidence, Checkout, CheckoutState
from agent_commerce.trust.models import (
    ApprovalRecord,
    ApprovalSource,
    ApprovalStatus,
    CheckoutProposal,
    CreateCheckoutProposalRequest,
    CreateSpendingMandateRequest,
    EvaluateProposalRequest,
    ExplicitApprovalRequest,
    MandateStatus,
    PolicyDecision,
    PolicyOutcome,
    ProposalStatus,
    RejectProposalRequest,
    RevokeMandateRequest,
    SpendingMandate,
)
from agent_commerce.trust.repository import InMemoryTrustRepository, TrustRepository

ModelT = TypeVar("ModelT", bound=BaseModel)


class TrustService:
    def __init__(
        self,
        repository: TrustRepository | None = None,
        audit: AuditLedger | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.repository = repository or InMemoryTrustRepository()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self.audit = audit or AuditLedger(clock=self._clock, id_factory=self._id_factory)

    def create_mandate(self, request: CreateSpendingMandateRequest) -> SpendingMandate:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "create_mandate", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, SpendingMandate)
            now = self._now()
            if request.valid_from >= request.expires_at:
                raise validation_error("Mandate expires_at must be after valid_from")
            if request.max_transaction_minor > request.max_total_minor:
                raise validation_error(
                    "Per-transaction limit cannot exceed the total mandate limit"
                )
            mandate = SpendingMandate(
                mandate_id=f"mandate_{self._id_factory()}",
                user_id=request.user_id,
                agent_id=request.agent_id,
                allowed_merchant_ids=request.allowed_merchant_ids,
                allowed_categories=request.allowed_categories,
                max_transaction_minor=request.max_transaction_minor,
                max_total_minor=request.max_total_minor,
                used_amount_minor=0,
                reserved_amount_minor=0,
                currency=request.currency,
                minimum_return_window_days=request.minimum_return_window_days,
                latest_delivery_date=request.latest_delivery_date,
                requires_final_approval=request.requires_final_approval,
                status=MandateStatus.ACTIVE,
                valid_from=request.valid_from,
                expires_at=request.expires_at,
                created_at=now,
                updated_at=now,
            )
            self.repository.save_mandate(mandate)
            self.repository.save_idempotent(
                "create_mandate", request.idempotency_key, fingerprint, mandate
            )
            self.audit.record(
                transaction_id=f"mandate:{mandate.mandate_id}",
                action="mandate.created",
                actor_type="user",
                actor_id=mandate.user_id,
                subject_type="spending_mandate",
                subject_id=mandate.mandate_id,
                data={
                    "max_transaction_minor": mandate.max_transaction_minor,
                    "max_total_minor": mandate.max_total_minor,
                    "currency": mandate.currency,
                },
            )
            return mandate

    def get_mandate(self, mandate_id: str) -> SpendingMandate:
        mandate = self.repository.get_mandate(mandate_id)
        if mandate is None:
            raise not_found("spending_mandate", mandate_id)
        if mandate.status is MandateStatus.ACTIVE and mandate.expires_at <= self._now():
            expired = mandate.model_copy(
                update={"status": MandateStatus.EXPIRED, "updated_at": self._now()}
            )
            self.repository.save_mandate(expired)
            return expired
        return mandate

    def revoke_mandate(self, request: RevokeMandateRequest) -> SpendingMandate:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "revoke_mandate", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, SpendingMandate)
            mandate = self.get_mandate(request.mandate_id)
            if mandate.user_id != request.user_id:
                raise CommerceError(code="APPROVAL_INVALID", message="User cannot revoke mandate")
            if mandate.status is MandateStatus.REVOKED:
                return mandate
            now = self._now()
            revoked = mandate.model_copy(
                update={
                    "status": MandateStatus.REVOKED,
                    "reserved_amount_minor": 0,
                    "updated_at": now,
                }
            )
            self.repository.save_mandate(revoked)
            for approval in self.repository.list_approvals(mandate.mandate_id):
                if approval.status is ApprovalStatus.APPROVED:
                    self.repository.save_approval(
                        approval.model_copy(
                            update={
                                "status": ApprovalStatus.REVOKED,
                                "updated_at": now,
                            }
                        )
                    )
            self.repository.save_idempotent(
                "revoke_mandate", request.idempotency_key, fingerprint, revoked
            )
            self.audit.record(
                transaction_id=f"mandate:{mandate.mandate_id}",
                action="mandate.revoked",
                actor_type="user",
                actor_id=request.user_id,
                subject_type="spending_mandate",
                subject_id=mandate.mandate_id,
            )
            return revoked

    def create_proposal(
        self, checkout: Checkout, request: CreateCheckoutProposalRequest
    ) -> CheckoutProposal:
        fingerprint = self._fingerprint(request, extra=checkout.model_dump_json())
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "create_proposal", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, CheckoutProposal)
            if checkout.checkout_id != request.checkout_id:
                raise validation_error("Proposal checkout_id does not match checkout")
            if checkout.state is not CheckoutState.DRAFT:
                raise conflict("Only a draft checkout can be proposed", state=checkout.state)
            if checkout.expires_at <= self._now():
                raise CommerceError(code="EXPIRED", message="Checkout has expired")
            now = self._now()
            proposal = CheckoutProposal(
                proposal_id=f"proposal_{self._id_factory()}",
                transaction_id=checkout.transaction_id,
                checkout_id=checkout.checkout_id,
                checkout_version=checkout.version,
                merchant_id=checkout.merchant_id,
                user_id=request.user_id,
                agent_id=request.agent_id,
                lines=checkout.lines,
                delivery_option=checkout.delivery_option,
                price=checkout.price,
                return_policy=checkout.return_policy,
                selection_reason=request.selection_reason,
                satisfied_constraints=request.satisfied_constraints,
                disclosed_compromises=request.disclosed_compromises,
                content_hash=self._proposal_hash(checkout),
                status=ProposalStatus.PENDING_APPROVAL,
                expires_at=checkout.expires_at,
                created_at=now,
                updated_at=now,
            )
            self.repository.save_proposal(proposal)
            self.repository.save_idempotent(
                "create_proposal", request.idempotency_key, fingerprint, proposal
            )
            self.audit.record(
                transaction_id=proposal.transaction_id,
                action="approval.requested",
                actor_type="agent",
                actor_id=proposal.agent_id,
                subject_type="checkout_proposal",
                subject_id=proposal.proposal_id,
                data={
                    "checkout_id": proposal.checkout_id,
                    "checkout_version": proposal.checkout_version,
                    "amount_minor": proposal.price.total_minor,
                    "currency": proposal.price.currency,
                    "content_hash": proposal.content_hash,
                },
            )
            return proposal

    def get_proposal(self, proposal_id: str) -> CheckoutProposal:
        proposal = self.repository.get_proposal(proposal_id)
        if proposal is None:
            raise not_found("checkout_proposal", proposal_id)
        if (
            proposal.status is ProposalStatus.PENDING_APPROVAL
            and proposal.expires_at <= self._now()
        ):
            expired = proposal.model_copy(
                update={"status": ProposalStatus.EXPIRED, "updated_at": self._now()}
            )
            self.repository.save_proposal(expired)
            return expired
        return proposal

    def evaluate_proposal(self, request: EvaluateProposalRequest) -> PolicyDecision:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "evaluate_proposal", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, PolicyDecision)
            proposal = self._require_pending_proposal(request.proposal_id)
            self._require_proposal_actors(proposal, request.user_id, request.agent_id)
            if request.mandate_id is None:
                decision = PolicyDecision(
                    outcome=PolicyOutcome.EXPLICIT_APPROVAL_REQUIRED,
                    reasons=("No spending mandate was supplied.",),
                    proposal=proposal,
                )
            else:
                mandate = self.get_mandate(request.mandate_id)
                violations = self._mandate_violations(mandate, proposal)
                if violations:
                    decision = PolicyDecision(
                        outcome=PolicyOutcome.DENIED,
                        reasons=tuple(violations),
                        proposal=proposal,
                    )
                elif mandate.requires_final_approval:
                    decision = PolicyDecision(
                        outcome=PolicyOutcome.EXPLICIT_APPROVAL_REQUIRED,
                        reasons=("The spending mandate requires final user approval.",),
                        proposal=proposal,
                    )
                else:
                    approval = self._grant_approval(
                        proposal,
                        source=ApprovalSource.SPENDING_MANDATE,
                        mandate=mandate,
                    )
                    decision = PolicyDecision(
                        outcome=PolicyOutcome.AUTO_APPROVED,
                        reasons=("Checkout is within the active spending mandate.",),
                        proposal=self.get_proposal(proposal.proposal_id),
                        approval=approval,
                    )
            self.repository.save_idempotent(
                "evaluate_proposal", request.idempotency_key, fingerprint, decision
            )
            return decision

    def approve_proposal(self, request: ExplicitApprovalRequest) -> ApprovalRecord:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "approve_proposal", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, ApprovalRecord)
            proposal = self._require_pending_proposal(request.proposal_id)
            if proposal.user_id != request.user_id:
                raise CommerceError(code="APPROVAL_INVALID", message="Approval user mismatch")
            if proposal.content_hash != request.approved_content_hash:
                raise CommerceError(
                    code="APPROVAL_INVALID",
                    message="Approved proposal content does not match current proposal",
                )
            mandate = None
            if request.mandate_id is not None:
                mandate = self.get_mandate(request.mandate_id)
                violations = self._mandate_violations(mandate, proposal)
                if violations:
                    raise CommerceError(
                        code="APPROVAL_INVALID",
                        message="Proposal is outside the supplied spending mandate",
                        details={"reasons": violations},
                    )
            approval = self._grant_approval(
                proposal,
                source=ApprovalSource.EXPLICIT_USER,
                mandate=mandate,
            )
            self.repository.save_idempotent(
                "approve_proposal", request.idempotency_key, fingerprint, approval
            )
            return approval

    def reject_proposal(self, request: RejectProposalRequest) -> CheckoutProposal:
        fingerprint = self._fingerprint(request)
        with self.repository.atomic():
            cached = self.repository.get_idempotent(
                "reject_proposal", request.idempotency_key, fingerprint
            )
            if cached is not None:
                return self._expect_type(cached, CheckoutProposal)
            proposal = self._require_pending_proposal(request.proposal_id)
            if proposal.user_id != request.user_id:
                raise CommerceError(code="APPROVAL_INVALID", message="Rejection user mismatch")
            rejected = proposal.model_copy(
                update={"status": ProposalStatus.REJECTED, "updated_at": self._now()}
            )
            self.repository.save_proposal(rejected)
            self.repository.save_idempotent(
                "reject_proposal", request.idempotency_key, fingerprint, rejected
            )
            self.audit.record(
                transaction_id=proposal.transaction_id,
                action="approval.rejected",
                actor_type="user",
                actor_id=request.user_id,
                subject_type="checkout_proposal",
                subject_id=proposal.proposal_id,
                data={"reason": request.reason},
            )
            return rejected

    def get_approval(self, approval_id: str) -> ApprovalRecord:
        approval = self.repository.get_approval(approval_id)
        if approval is None:
            raise not_found("approval", approval_id)
        if approval.status is ApprovalStatus.APPROVED and approval.expires_at <= self._now():
            expired = approval.model_copy(
                update={"status": ApprovalStatus.EXPIRED, "updated_at": self._now()}
            )
            self.repository.save_approval(expired)
            self._release_mandate_reservation(expired)
            return expired
        return approval

    def get_approval_evidence(self, approval_id: str) -> ApprovalEvidence:
        approval = self.get_approval(approval_id)
        proposal = self.get_proposal(approval.proposal_id)
        if approval.status is not ApprovalStatus.APPROVED:
            raise CommerceError(code="APPROVAL_INVALID", message="Approval is not active")
        if proposal.status is not ProposalStatus.APPROVED:
            raise CommerceError(code="APPROVAL_INVALID", message="Proposal is not approved")
        if proposal.content_hash != approval.proposal_hash:
            raise CommerceError(code="APPROVAL_INVALID", message="Proposal hash mismatch")
        return ApprovalEvidence(
            approval_id=approval.approval_id,
            checkout_id=approval.checkout_id,
            checkout_version=approval.checkout_version,
            merchant_id=approval.merchant_id,
            amount_minor=approval.amount_minor,
            currency=approval.currency,
            expires_at=approval.expires_at,
        )

    def invalidate_checkout(self, checkout_id: str, current_version: int) -> int:
        invalidated = 0
        with self.repository.atomic():
            now = self._now()
            for proposal in self.repository.list_proposals(checkout_id):
                if proposal.checkout_version == current_version:
                    continue
                if proposal.status not in {
                    ProposalStatus.PENDING_APPROVAL,
                    ProposalStatus.APPROVED,
                }:
                    continue
                self.repository.save_proposal(
                    proposal.model_copy(
                        update={"status": ProposalStatus.INVALIDATED, "updated_at": now}
                    )
                )
                approval = self.repository.get_approval_by_proposal(proposal.proposal_id)
                if approval is not None and approval.status is ApprovalStatus.APPROVED:
                    invalid_approval = approval.model_copy(
                        update={"status": ApprovalStatus.INVALIDATED, "updated_at": now}
                    )
                    self.repository.save_approval(invalid_approval)
                    self._release_mandate_reservation(invalid_approval)
                self.audit.record(
                    transaction_id=proposal.transaction_id,
                    action="approval.invalidated",
                    actor_type="system",
                    actor_id="checkout-version-guard",
                    subject_type="checkout_proposal",
                    subject_id=proposal.proposal_id,
                    data={"current_checkout_version": current_version},
                )
                invalidated += 1
        return invalidated

    def record_captured_spend(
        self,
        approval_id: str,
        payment_id: str,
        amount_minor: int,
        currency: str,
    ) -> SpendingMandate | None:
        approval = self.get_approval(approval_id)
        if approval.status is not ApprovalStatus.APPROVED:
            raise CommerceError(code="APPROVAL_INVALID", message="Approval is not active")
        if approval.mandate_id is None:
            return None
        fingerprint = hashlib.sha256(
            f"{approval_id}:{payment_id}:{amount_minor}:{currency}".encode()
        ).hexdigest()
        with self.repository.atomic():
            cached = self.repository.get_idempotent("record_spend", payment_id, fingerprint)
            if cached is not None:
                return self._expect_type(cached, SpendingMandate)
            mandate = self.get_mandate(approval.mandate_id)
            if amount_minor != approval.amount_minor or currency != approval.currency:
                raise CommerceError(
                    code="APPROVAL_INVALID",
                    message="Captured spend does not match approved amount",
                )
            updated = mandate.model_copy(
                update={
                    "reserved_amount_minor": max(0, mandate.reserved_amount_minor - amount_minor),
                    "used_amount_minor": mandate.used_amount_minor + amount_minor,
                    "updated_at": self._now(),
                }
            )
            self.repository.save_mandate(updated)
            self.repository.save_idempotent("record_spend", payment_id, fingerprint, updated)
            return updated

    def record_refund(
        self,
        approval_id: str,
        refund_id: str,
        amount_minor: int,
        currency: str,
    ) -> SpendingMandate | None:
        approval = self.get_approval(approval_id)
        if approval.mandate_id is None:
            return None
        fingerprint = hashlib.sha256(
            f"{approval_id}:{refund_id}:{amount_minor}:{currency}".encode()
        ).hexdigest()
        with self.repository.atomic():
            cached = self.repository.get_idempotent("record_refund", refund_id, fingerprint)
            if cached is not None:
                return self._expect_type(cached, SpendingMandate)
            mandate = self.get_mandate(approval.mandate_id)
            if currency != mandate.currency or amount_minor > mandate.used_amount_minor:
                raise CommerceError(
                    code="APPROVAL_INVALID",
                    message="Refund cannot be applied to the spending mandate",
                )
            updated = mandate.model_copy(
                update={
                    "used_amount_minor": mandate.used_amount_minor - amount_minor,
                    "updated_at": self._now(),
                }
            )
            self.repository.save_mandate(updated)
            self.repository.save_idempotent("record_refund", refund_id, fingerprint, updated)
            return updated

    def invalidate_approval(self, approval_id: str, *, reason: str) -> ApprovalRecord:
        with self.repository.atomic():
            approval = self.get_approval(approval_id)
            if approval.status is ApprovalStatus.INVALIDATED:
                return approval
            if approval.status is not ApprovalStatus.APPROVED:
                raise conflict("Only an active approval can be invalidated", status=approval.status)
            now = self._now()
            invalidated = approval.model_copy(
                update={"status": ApprovalStatus.INVALIDATED, "updated_at": now}
            )
            self.repository.save_approval(invalidated)
            proposal = self.get_proposal(approval.proposal_id)
            if proposal.status is ProposalStatus.APPROVED:
                self.repository.save_proposal(
                    proposal.model_copy(
                        update={"status": ProposalStatus.INVALIDATED, "updated_at": now}
                    )
                )
            self._release_mandate_reservation(invalidated)
            self.audit.record(
                transaction_id=approval.transaction_id,
                action="approval.invalidated",
                actor_type="system",
                actor_id="payment-recovery",
                subject_type="approval",
                subject_id=approval.approval_id,
                data={"reason": reason},
            )
            return invalidated

    def _grant_approval(
        self,
        proposal: CheckoutProposal,
        *,
        source: ApprovalSource,
        mandate: SpendingMandate | None,
    ) -> ApprovalRecord:
        if source is ApprovalSource.SPENDING_MANDATE and mandate is None:
            raise RuntimeError("Mandate approval source requires a mandate")
        existing = self.repository.get_approval_by_proposal(proposal.proposal_id)
        if existing is not None:
            return existing
        now = self._now()
        approval = ApprovalRecord(
            approval_id=f"approval_{self._id_factory()}",
            proposal_id=proposal.proposal_id,
            transaction_id=proposal.transaction_id,
            checkout_id=proposal.checkout_id,
            checkout_version=proposal.checkout_version,
            merchant_id=proposal.merchant_id,
            user_id=proposal.user_id,
            agent_id=proposal.agent_id,
            amount_minor=proposal.price.total_minor,
            currency=proposal.price.currency,
            proposal_hash=proposal.content_hash,
            source=source,
            mandate_id=mandate.mandate_id if mandate else None,
            status=ApprovalStatus.APPROVED,
            expires_at=(
                min(proposal.expires_at, mandate.expires_at)
                if mandate is not None
                else proposal.expires_at
            ),
            created_at=now,
            updated_at=now,
        )
        approved_proposal = proposal.model_copy(
            update={"status": ProposalStatus.APPROVED, "updated_at": now}
        )
        self.repository.save_approval(approval)
        self.repository.save_proposal(approved_proposal)
        if mandate is not None:
            self.repository.save_mandate(
                mandate.model_copy(
                    update={
                        "reserved_amount_minor": mandate.reserved_amount_minor
                        + approval.amount_minor,
                        "updated_at": now,
                    }
                )
            )
        audit_actor_id = proposal.user_id
        if source is ApprovalSource.SPENDING_MANDATE:
            if mandate is None:
                raise RuntimeError("Mandate approval source requires a mandate")
            audit_actor_id = mandate.mandate_id
        self.audit.record(
            transaction_id=proposal.transaction_id,
            action="approval.granted",
            actor_type="user" if source is ApprovalSource.EXPLICIT_USER else "policy",
            actor_id=audit_actor_id,
            subject_type="approval",
            subject_id=approval.approval_id,
            data={
                "checkout_id": approval.checkout_id,
                "checkout_version": approval.checkout_version,
                "amount_minor": approval.amount_minor,
                "currency": approval.currency,
                "source": approval.source,
            },
        )
        return approval

    def _mandate_violations(
        self, mandate: SpendingMandate, proposal: CheckoutProposal
    ) -> list[str]:
        now = self._now()
        violations: list[str] = []
        if mandate.status is not MandateStatus.ACTIVE:
            violations.append("Spending mandate is not active.")
        if not (mandate.valid_from <= now < mandate.expires_at):
            violations.append("Spending mandate is outside its validity window.")
        if mandate.user_id != proposal.user_id or mandate.agent_id != proposal.agent_id:
            violations.append("Spending mandate actor does not match proposal actors.")
        if (
            mandate.allowed_merchant_ids
            and proposal.merchant_id not in mandate.allowed_merchant_ids
        ):
            violations.append("Merchant is not permitted by the spending mandate.")
        categories = {line.product_category for line in proposal.lines}
        if mandate.allowed_categories and not categories <= mandate.allowed_categories:
            violations.append("Product category is not permitted by the spending mandate.")
        if proposal.price.currency != mandate.currency:
            violations.append("Checkout currency does not match the spending mandate.")
        if proposal.price.total_minor > mandate.max_transaction_minor:
            violations.append("Checkout exceeds the per-transaction spending limit.")
        projected = (
            mandate.used_amount_minor + mandate.reserved_amount_minor + proposal.price.total_minor
        )
        if projected > mandate.max_total_minor:
            violations.append("Checkout exceeds the remaining cumulative spending limit.")
        if proposal.return_policy.window_days < mandate.minimum_return_window_days:
            violations.append("Return window is shorter than the mandate requires.")
        if (
            mandate.latest_delivery_date is not None
            and proposal.delivery_option.estimated_delivery_date > mandate.latest_delivery_date
        ):
            violations.append("Delivery date is later than the mandate permits.")
        return violations

    def _require_pending_proposal(self, proposal_id: str) -> CheckoutProposal:
        proposal = self.get_proposal(proposal_id)
        if proposal.status is ProposalStatus.EXPIRED:
            raise CommerceError(code="EXPIRED", message="Checkout proposal has expired")
        if proposal.status is not ProposalStatus.PENDING_APPROVAL:
            raise conflict("Checkout proposal is not pending approval", status=proposal.status)
        return proposal

    @staticmethod
    def _require_proposal_actors(proposal: CheckoutProposal, user_id: str, agent_id: str) -> None:
        if proposal.user_id != user_id or proposal.agent_id != agent_id:
            raise CommerceError(code="APPROVAL_INVALID", message="Proposal actor mismatch")

    def _release_mandate_reservation(self, approval: ApprovalRecord) -> None:
        if approval.mandate_id is None:
            return
        mandate = self.repository.get_mandate(approval.mandate_id)
        if mandate is None:
            return
        self.repository.save_mandate(
            mandate.model_copy(
                update={
                    "reserved_amount_minor": max(
                        0, mandate.reserved_amount_minor - approval.amount_minor
                    ),
                    "updated_at": self._now(),
                }
            )
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise RuntimeError("Trust clock must return a timezone-aware datetime")
        return value

    @staticmethod
    def _proposal_hash(checkout: Checkout) -> str:
        exact = checkout.model_dump_json(
            include={
                "checkout_id",
                "transaction_id",
                "merchant_id",
                "version",
                "lines",
                "delivery_option",
                "price",
                "return_policy",
                "expires_at",
            }
        )
        return hashlib.sha256(exact.encode()).hexdigest()

    @staticmethod
    def _fingerprint(request: BaseModel, *, extra: str = "") -> str:
        canonical = request.model_dump_json(exclude={"idempotency_key"}) + extra
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _expect_type(value: object, expected: type[ModelT]) -> ModelT:
        if not isinstance(value, expected):
            raise RuntimeError(f"Corrupt idempotency record: expected {expected.__name__}")
        return value
