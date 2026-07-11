"""Trust repository contracts and in-memory implementation."""

from __future__ import annotations

from contextlib import AbstractContextManager
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol

from agent_commerce.commerce.errors import CommerceError
from agent_commerce.trust.models import ApprovalRecord, CheckoutProposal, SpendingMandate


class TrustRepository(Protocol):
    def atomic(self) -> AbstractContextManager[None]: ...

    def get_mandate(self, mandate_id: str) -> SpendingMandate | None: ...

    def save_mandate(self, mandate: SpendingMandate) -> None: ...

    def get_proposal(self, proposal_id: str) -> CheckoutProposal | None: ...

    def list_proposals(self, checkout_id: str | None = None) -> list[CheckoutProposal]: ...

    def save_proposal(self, proposal: CheckoutProposal) -> None: ...

    def get_approval(self, approval_id: str) -> ApprovalRecord | None: ...

    def get_approval_by_proposal(self, proposal_id: str) -> ApprovalRecord | None: ...

    def list_approvals(self, mandate_id: str | None = None) -> list[ApprovalRecord]: ...

    def save_approval(self, approval: ApprovalRecord) -> None: ...

    def get_idempotent(self, operation: str, key: str, fingerprint: str) -> Any | None: ...

    def save_idempotent(self, operation: str, key: str, fingerprint: str, value: Any) -> None: ...


@dataclass
class InMemoryTrustRepository:
    mandates: dict[str, SpendingMandate] = field(default_factory=dict)
    proposals: dict[str, CheckoutProposal] = field(default_factory=dict)
    approvals: dict[str, ApprovalRecord] = field(default_factory=dict)
    idempotency: dict[tuple[str, str], tuple[str, Any]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def atomic(self) -> AbstractContextManager[None]:
        return self._lock

    def get_mandate(self, mandate_id: str) -> SpendingMandate | None:
        value = self.mandates.get(mandate_id)
        return deepcopy(value) if value else None

    def save_mandate(self, mandate: SpendingMandate) -> None:
        self.mandates[mandate.mandate_id] = deepcopy(mandate)

    def get_proposal(self, proposal_id: str) -> CheckoutProposal | None:
        value = self.proposals.get(proposal_id)
        return deepcopy(value) if value else None

    def list_proposals(self, checkout_id: str | None = None) -> list[CheckoutProposal]:
        values = list(self.proposals.values())
        if checkout_id is not None:
            values = [proposal for proposal in values if proposal.checkout_id == checkout_id]
        return deepcopy(values)

    def save_proposal(self, proposal: CheckoutProposal) -> None:
        self.proposals[proposal.proposal_id] = deepcopy(proposal)

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        value = self.approvals.get(approval_id)
        return deepcopy(value) if value else None

    def get_approval_by_proposal(self, proposal_id: str) -> ApprovalRecord | None:
        for approval in self.approvals.values():
            if approval.proposal_id == proposal_id:
                return deepcopy(approval)
        return None

    def list_approvals(self, mandate_id: str | None = None) -> list[ApprovalRecord]:
        values = list(self.approvals.values())
        if mandate_id is not None:
            values = [approval for approval in values if approval.mandate_id == mandate_id]
        return deepcopy(values)

    def save_approval(self, approval: ApprovalRecord) -> None:
        self.approvals[approval.approval_id] = deepcopy(approval)

    def get_idempotent(self, operation: str, key: str, fingerprint: str) -> Any | None:
        stored = self.idempotency.get((operation, key))
        if stored is None:
            return None
        stored_fingerprint, value = stored
        if stored_fingerprint != fingerprint:
            raise CommerceError(
                code="IDEMPOTENCY_CONFLICT",
                message="Idempotency key was reused with a different request",
                details={"operation": operation, "idempotency_key": key},
            )
        return deepcopy(value)

    def save_idempotent(self, operation: str, key: str, fingerprint: str, value: Any) -> None:
        self.idempotency[(operation, key)] = (fingerprint, deepcopy(value))
