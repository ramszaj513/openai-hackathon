"""End-to-end agent transaction orchestration."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel

from agent_commerce.audit import AuditLedger
from agent_commerce.commerce.errors import CommerceError, conflict, not_found
from agent_commerce.commerce.models import (
    CancelOrderRequest,
    CompleteCheckoutRequest,
    CreateCheckoutRequest,
    CreateReturnRequest,
    OfferSelection,
    OrderState,
)
from agent_commerce.orchestration.activity import (
    ActivityPhase,
    ActivityReporter,
    ActivityStatus,
    TransactionActivity,
    TransactionActivityLog,
)
from agent_commerce.orchestration.brain import IntentInterpreter, OfferPlanner
from agent_commerce.orchestration.merchant_gateway import (
    AmbiguousMerchantError,
    MerchantGateway,
)
from agent_commerce.orchestration.models import (
    AgentTransaction,
    ApproveTransactionRequest,
    CancelTransactionRequest,
    ReturnTransactionRequest,
    StartPurchaseRequest,
    TransactionState,
    TransitionRecord,
)
from agent_commerce.orchestration.repository import (
    InMemoryTransactionRepository,
    TransactionRepository,
)
from agent_commerce.orchestration.state_machine import transition
from agent_commerce.payments import PaymentService
from agent_commerce.payments.models import (
    AuthorizePaymentRequest,
    CapturePaymentRequest,
    IssuePaymentCredentialRequest,
    PaymentStatus,
    RecoverAuthorizationRequest,
    RefundPaymentRequest,
)
from agent_commerce.trust import TrustService
from agent_commerce.trust.models import (
    CreateCheckoutProposalRequest,
    EvaluateProposalRequest,
    ExplicitApprovalRequest,
    PolicyOutcome,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True)
class TransactionSubmission:
    transaction: AgentTransaction
    fingerprint: str
    should_process: bool


STATE_PHASES: dict[TransactionState, ActivityPhase] = {
    TransactionState.INTENT_CAPTURED: ActivityPhase.INTENT,
    TransactionState.CLARIFICATION_REQUIRED: ActivityPhase.INTENT,
    TransactionState.DISCOVERING: ActivityPhase.DISCOVERY,
    TransactionState.NO_MATCH: ActivityPhase.DISCOVERY,
    TransactionState.OFFER_SELECTED: ActivityPhase.DISCOVERY,
    TransactionState.CHECKOUT_DRAFT: ActivityPhase.CHECKOUT,
    TransactionState.APPROVAL_PENDING: ActivityPhase.APPROVAL,
    TransactionState.APPROVED: ActivityPhase.APPROVAL,
    TransactionState.PAYMENT_AUTHORIZING: ActivityPhase.PAYMENT,
    TransactionState.PAYMENT_AUTHORIZED: ActivityPhase.PAYMENT,
    TransactionState.ORDER_COMMITTING: ActivityPhase.ORDER,
    TransactionState.RECOVERY_REQUIRED: ActivityPhase.ORDER,
    TransactionState.ORDER_CONFIRMED: ActivityPhase.ORDER,
    TransactionState.PAYMENT_CAPTURED: ActivityPhase.PAYMENT,
    TransactionState.FULFILLING: ActivityPhase.FULFILLMENT,
    TransactionState.DELIVERED: ActivityPhase.FULFILLMENT,
    TransactionState.CANCELLATION_REQUESTED: ActivityPhase.RESOLUTION,
    TransactionState.CANCELLED: ActivityPhase.RESOLUTION,
    TransactionState.RETURN_REQUESTED: ActivityPhase.RESOLUTION,
    TransactionState.REFUND_PENDING: ActivityPhase.RESOLUTION,
    TransactionState.REFUNDED: ActivityPhase.RESOLUTION,
    TransactionState.FAILED: ActivityPhase.SYSTEM,
}


class CommerceOrchestrator:
    def __init__(
        self,
        *,
        merchant: MerchantGateway,
        trust: TrustService,
        payments: PaymentService,
        intent_interpreter: IntentInterpreter,
        offer_planner: OfferPlanner,
        repository: TransactionRepository | None = None,
        audit: AuditLedger | None = None,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
        autonomous_confidence_threshold: float = 0.9,
        activities: TransactionActivityLog | None = None,
    ) -> None:
        self.merchant = merchant
        self.trust = trust
        self.payments = payments
        self.intent_interpreter = intent_interpreter
        self.offer_planner = offer_planner
        self.repository = repository or InMemoryTransactionRepository()
        self.audit = audit or trust.audit
        self._clock = clock or (lambda: datetime.now(UTC))
        self.activities = activities or TransactionActivityLog(clock=self._clock)
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self.autonomous_confidence_threshold = autonomous_confidence_threshold

    async def start(self, request: StartPurchaseRequest) -> AgentTransaction:
        submission = self.begin(request)
        if not submission.should_process:
            return submission.transaction
        return await self.process(
            request,
            submission.transaction.transaction_id,
            submission.fingerprint,
        )

    def begin(self, request: StartPurchaseRequest) -> TransactionSubmission:
        """Persist and return a transaction before model processing begins."""
        fingerprint = self._fingerprint(request)
        cached = self.repository.get_idempotent(
            "start_purchase", request.idempotency_key, fingerprint
        )
        if cached is not None:
            return TransactionSubmission(
                transaction=self._expect_type(cached, AgentTransaction),
                fingerprint=fingerprint,
                should_process=False,
            )
        now = self._now()
        transaction = AgentTransaction(
            transaction_id=f"txn_{self._id_factory()}",
            user_id=request.user_id,
            agent_id=request.agent_id,
            raw_request=request.raw_request,
            mandate_id=request.mandate_id,
            payment_scenario=request.payment_scenario,
            state=TransactionState.INTENT_CAPTURED,
            transitions=(
                TransitionRecord(
                    from_state=None,
                    to_state=TransactionState.INTENT_CAPTURED,
                    occurred_at=now,
                    reason="User purchase request captured.",
                ),
            ),
            created_at=now,
            updated_at=now,
        )
        self.repository.save(transaction)
        self.repository.save_idempotent(
            "start_purchase", request.idempotency_key, fingerprint, transaction
        )
        self.activities.record(
            transaction_id=transaction.transaction_id,
            kind="transaction.created",
            phase=ActivityPhase.INTENT,
            status=ActivityStatus.STARTED,
            title="Purchase request captured",
            message="The agent transaction was created and queued for processing.",
            actor_type="user",
            actor_id=transaction.user_id,
            authority="orchestrator",
        )
        return TransactionSubmission(
            transaction=transaction,
            fingerprint=fingerprint,
            should_process=True,
        )

    async def process(
        self,
        request: StartPurchaseRequest,
        transaction_id: str,
        fingerprint: str,
    ) -> AgentTransaction:
        """Run model, merchant, policy, and optional autonomous execution work."""
        transaction = self.get(transaction_id)
        reporter = ActivityReporter(self.activities, transaction_id, transaction.agent_id)
        try:
            reporter.record(
                kind="agent.intent.started",
                phase=ActivityPhase.INTENT,
                status=ActivityStatus.STARTED,
                title="Understanding purchase intent",
                message="The model is converting the request into structured constraints.",
            )
            intent = await self.intent_interpreter.normalize(request.raw_request, reporter)
            reporter.record(
                kind="agent.intent.completed",
                phase=ActivityPhase.INTENT,
                status=ActivityStatus.COMPLETED,
                title="Purchase intent structured",
                message="The request is now represented as typed transaction constraints.",
                data={
                    "product_query": intent.product_query,
                    "category": intent.category,
                    "quantity": intent.quantity,
                    "currency": intent.currency,
                    "missing_required_fields": list(intent.missing_required_fields),
                },
            )
            transaction = transaction.model_copy(
                update={"intent": intent, "updated_at": self._now()}
            )
            self.repository.save(transaction)
            if intent.missing_required_fields:
                transaction = self._transition(
                    transaction,
                    TransactionState.CLARIFICATION_REQUIRED,
                    "Required purchase constraints are missing.",
                )
                return self._cache_start(request, fingerprint, transaction)

            transaction = self._transition(
                transaction,
                TransactionState.DISCOVERING,
                "Agent is discovering and evaluating merchant offers.",
            )
            selection = await self.offer_planner.select(intent, reporter)
            reporter.record(
                kind="agent.selection.completed",
                phase=ActivityPhase.DISCOVERY,
                status=(
                    ActivityStatus.SUCCEEDED
                    if selection.selected_offer_id is not None
                    else ActivityStatus.COMPLETED
                ),
                title=(
                    "Offer selected"
                    if selection.selected_offer_id is not None
                    else "No suitable offer found"
                ),
                message=selection.selection_reason,
                data={
                    "selected_offer_id": selection.selected_offer_id,
                    "confidence": selection.confidence,
                    "rejected_offer_count": len(selection.rejected_offers),
                },
            )
            if selection.selected_offer_id is None:
                transaction = self._transition(
                    transaction,
                    TransactionState.NO_MATCH,
                    selection.selection_reason,
                    updates={"selection": selection},
                )
                return self._cache_start(request, fingerprint, transaction)
            offer = await self.merchant.get_offer(selection.selected_offer_id)
            if selection.selected_offer_version != offer.version:
                transaction = self._fail(
                    transaction,
                    "STALE_VERSION",
                    "Selected offer changed before checkout creation.",
                )
                return self._cache_start(request, fingerprint, transaction)
            if selection.delivery_option_id is None:
                transaction = self._fail(
                    transaction,
                    "VALIDATION_ERROR",
                    "Agent did not select a delivery option.",
                )
                return self._cache_start(request, fingerprint, transaction)
            transaction = self._transition(
                transaction,
                TransactionState.OFFER_SELECTED,
                selection.selection_reason,
                updates={"selection": selection, "selected_offer": offer},
            )
            checkout = await self.merchant.create_checkout(
                CreateCheckoutRequest(
                    transaction_id=transaction.transaction_id,
                    selections=(
                        OfferSelection(
                            offer_id=offer.offer_id,
                            offer_version=offer.version,
                            quantity=intent.quantity,
                        ),
                    ),
                    delivery_option_id=selection.delivery_option_id,
                    idempotency_key=f"{transaction.transaction_id}:create-checkout",
                )
            )
            transaction = self._transition(
                transaction,
                TransactionState.CHECKOUT_DRAFT,
                "Merchant created an authoritative checkout.",
                updates={"checkout": checkout},
            )
            proposal = self.trust.create_proposal(
                checkout,
                CreateCheckoutProposalRequest(
                    checkout_id=checkout.checkout_id,
                    user_id=transaction.user_id,
                    agent_id=transaction.agent_id,
                    selection_reason=selection.selection_reason,
                    satisfied_constraints=selection.satisfied_constraints,
                    disclosed_compromises=selection.disclosed_compromises,
                    idempotency_key=f"{transaction.transaction_id}:proposal",
                ),
            )
            transaction = self._transition(
                transaction,
                TransactionState.APPROVAL_PENDING,
                "Exact checkout proposal is ready for policy evaluation or user approval.",
                updates={"proposal": proposal},
            )
            may_auto_execute = (
                intent.purchase_if_confident
                and selection.confidence >= self.autonomous_confidence_threshold
            )
            decision = self.trust.evaluate_proposal(
                EvaluateProposalRequest(
                    proposal_id=proposal.proposal_id,
                    user_id=transaction.user_id,
                    agent_id=transaction.agent_id,
                    mandate_id=request.mandate_id if may_auto_execute else None,
                    idempotency_key=f"{transaction.transaction_id}:policy-evaluation",
                )
            )
            if decision.outcome is PolicyOutcome.DENIED:
                transaction = self._fail(
                    transaction,
                    "POLICY_DENIED",
                    " ".join(decision.reasons),
                )
            elif decision.outcome is PolicyOutcome.AUTO_APPROVED:
                if decision.approval is None:
                    raise RuntimeError("Auto-approved decision did not include approval")
                transaction = self._transition(
                    transaction,
                    TransactionState.APPROVED,
                    "Active spending mandate approved the exact checkout.",
                    updates={"approval_id": decision.approval.approval_id},
                )
                transaction = await self._execute_approved(transaction)
            return self._cache_start(request, fingerprint, transaction)
        except CommerceError as exc:
            transaction = self._fail(transaction, exc.code, exc.message)
            return self._cache_start(request, fingerprint, transaction)
        except Exception as exc:
            transaction = self._fail(
                transaction,
                "AGENT_EXECUTION_ERROR",
                str(exc),
            )
            return self._cache_start(request, fingerprint, transaction)

    async def approve(self, request: ApproveTransactionRequest) -> AgentTransaction:
        fingerprint = self._fingerprint(request)
        cached = self.repository.get_idempotent(
            "approve_transaction", request.idempotency_key, fingerprint
        )
        if cached is not None:
            return self._expect_type(cached, AgentTransaction)
        transaction = self.get(request.transaction_id)
        if transaction.state is not TransactionState.APPROVAL_PENDING:
            raise conflict("Transaction is not waiting for approval", state=transaction.state)
        if transaction.user_id != request.user_id or transaction.proposal is None:
            raise CommerceError(code="APPROVAL_INVALID", message="Approval actor mismatch")
        approval = self.trust.approve_proposal(
            ExplicitApprovalRequest(
                proposal_id=transaction.proposal.proposal_id,
                user_id=request.user_id,
                approved_content_hash=request.approved_content_hash,
                mandate_id=request.mandate_id,
                idempotency_key=f"{transaction.transaction_id}:explicit-approval",
            )
        )
        transaction = self._transition(
            transaction,
            TransactionState.APPROVED,
            "User explicitly approved the exact checkout proposal.",
            updates={"approval_id": approval.approval_id},
        )
        transaction = await self._execute_approved(transaction)
        self.repository.save_idempotent(
            "approve_transaction", request.idempotency_key, fingerprint, transaction
        )
        return transaction

    async def resume_from_events(self, transaction_id: str) -> AgentTransaction:
        transaction = self.get(transaction_id)
        events = await self.merchant.list_events(transaction_id)
        unseen = [event for event in events if event.event_id not in transaction.seen_event_ids]
        seen = set(transaction.seen_event_ids)
        for event in unseen:
            seen.add(event.event_id)
            if event.event_type != "order.fulfillment_updated":
                continue
            state = str(event.payload.get("state", ""))
            if state == OrderState.DELIVERED and transaction.state is TransactionState.FULFILLING:
                transaction = self._transition(
                    transaction,
                    TransactionState.DELIVERED,
                    "Merchant reported that the order was delivered.",
                )
        transaction = transaction.model_copy(
            update={"seen_event_ids": frozenset(seen), "updated_at": self._now()}
        )
        self.repository.save(transaction)
        return transaction

    async def cancel(self, request: CancelTransactionRequest) -> AgentTransaction:
        fingerprint = self._fingerprint(request)
        cached = self.repository.get_idempotent(
            "cancel_transaction", request.idempotency_key, fingerprint
        )
        if cached is not None:
            return self._expect_type(cached, AgentTransaction)
        transaction = self.get(request.transaction_id)
        if transaction.state is not TransactionState.FULFILLING:
            raise conflict("Only a fulfilling order can be cancelled", state=transaction.state)
        if transaction.order_id is None or transaction.payment_id is None:
            raise RuntimeError("Transaction is missing order or payment reference")
        order_id = transaction.order_id
        payment_id = transaction.payment_id
        transaction = self._transition(
            transaction,
            TransactionState.CANCELLATION_REQUESTED,
            request.reason,
        )
        await self.merchant.cancel_order(
            CancelOrderRequest(
                order_id=order_id,
                idempotency_key=f"{transaction.transaction_id}:merchant-cancel",
            )
        )
        transaction = self._transition(
            transaction,
            TransactionState.CANCELLED,
            "Merchant cancelled the order.",
        )
        transaction = self._transition(
            transaction,
            TransactionState.REFUND_PENDING,
            "Captured payment must be refunded after cancellation.",
        )
        payment = self.payments.get_payment(payment_id)
        self.payments.refund(
            RefundPaymentRequest(
                payment_id=payment.payment_id,
                order_id=order_id,
                amount_minor=payment.captured_amount_minor - payment.refunded_amount_minor,
                reason=request.reason,
                idempotency_key=f"{transaction.transaction_id}:cancel-refund",
            )
        )
        transaction = self._transition(
            transaction,
            TransactionState.REFUNDED,
            "Cancellation refund completed.",
        )
        self.repository.save_idempotent(
            "cancel_transaction", request.idempotency_key, fingerprint, transaction
        )
        return transaction

    async def return_order(self, request: ReturnTransactionRequest) -> AgentTransaction:
        fingerprint = self._fingerprint(request)
        cached = self.repository.get_idempotent(
            "return_transaction", request.idempotency_key, fingerprint
        )
        if cached is not None:
            return self._expect_type(cached, AgentTransaction)
        transaction = self.get(request.transaction_id)
        if transaction.state is not TransactionState.DELIVERED:
            raise conflict("Only a delivered order can be returned", state=transaction.state)
        if transaction.order_id is None or transaction.payment_id is None:
            raise RuntimeError("Transaction is missing order or payment reference")
        order_id = transaction.order_id
        payment_id = transaction.payment_id
        transaction = self._transition(
            transaction,
            TransactionState.RETURN_REQUESTED,
            request.reason,
        )
        record = await self.merchant.create_return(
            CreateReturnRequest(
                order_id=order_id,
                items=request.items,
                reason=request.reason,
                idempotency_key=f"{transaction.transaction_id}:merchant-return",
            )
        )
        transaction = self._transition(
            transaction,
            TransactionState.REFUND_PENDING,
            "Merchant authorized the return and requested a refund.",
            updates={"return_id": record.return_id},
        )
        self.payments.refund(
            RefundPaymentRequest(
                payment_id=payment_id,
                order_id=order_id,
                amount_minor=record.refund_amount.amount_minor,
                reason=request.reason,
                idempotency_key=f"{transaction.transaction_id}:return-refund",
            )
        )
        transaction = self._transition(
            transaction,
            TransactionState.REFUNDED,
            "Return refund completed.",
        )
        self.repository.save_idempotent(
            "return_transaction", request.idempotency_key, fingerprint, transaction
        )
        return transaction

    def get(self, transaction_id: str) -> AgentTransaction:
        transaction = self.repository.get(transaction_id)
        if transaction is None:
            raise not_found("agent_transaction", transaction_id)
        return transaction

    def list_activities(
        self,
        transaction_id: str,
        *,
        after_sequence: int = 0,
    ) -> list[TransactionActivity]:
        self.get(transaction_id)
        return self.activities.list(transaction_id, after_sequence=after_sequence)

    async def _execute_approved(self, transaction: AgentTransaction) -> AgentTransaction:
        if transaction.approval_id is None or transaction.checkout is None:
            raise RuntimeError("Approved transaction is missing approval or checkout")
        approval_id = transaction.approval_id
        checkout = transaction.checkout
        transaction = self._transition(
            transaction,
            TransactionState.PAYMENT_AUTHORIZING,
            "Issuing a single-use credential and requesting payment authorization.",
        )
        credential = self.payments.issue_credential(
            IssuePaymentCredentialRequest(
                approval_id=approval_id,
                user_id=transaction.user_id,
                idempotency_key=f"{transaction.transaction_id}:payment-credential",
            )
        )
        authorization = self.payments.authorize(
            AuthorizePaymentRequest(
                credential_id=credential.credential_id,
                approval_id=approval_id,
                scenario=transaction.payment_scenario,
                idempotency_key=f"{transaction.transaction_id}:payment-authorization",
            )
        )
        transaction = transaction.model_copy(
            update={
                "credential_id": credential.credential_id,
                "payment_id": authorization.payment.payment_id,
                "updated_at": self._now(),
            }
        )
        self.repository.save(transaction)
        if authorization.payment.status is PaymentStatus.DECLINED:
            return self._fail(transaction, "PAYMENT_DECLINED", "Payment was declined.")
        if authorization.merchant_reference is None:
            return self._fail(
                transaction,
                "PAYMENT_DECLINED",
                "Payment provider did not return merchant authorization.",
            )
        transaction = self._transition(
            transaction,
            TransactionState.PAYMENT_AUTHORIZED,
            "Payment is authorized for the exact approved checkout.",
        )
        transaction = self._transition(
            transaction,
            TransactionState.ORDER_COMMITTING,
            "Submitting the authorized checkout to the merchant.",
        )
        evidence = self.trust.get_approval_evidence(approval_id)
        try:
            order = await self.merchant.complete_checkout(
                CompleteCheckoutRequest(
                    checkout_id=checkout.checkout_id,
                    expected_version=checkout.version,
                    approval=evidence,
                    payment_authorization=authorization.merchant_reference,
                    idempotency_key=f"{transaction.transaction_id}:complete-checkout",
                )
            )
        except AmbiguousMerchantError:
            return await self._recover_ambiguous_completion(transaction)
        except CommerceError as exc:
            self.payments.recover_authorization(
                RecoverAuthorizationRequest(
                    payment_id=authorization.payment.payment_id,
                    reconciled_order_id=None,
                    idempotency_key=f"{transaction.transaction_id}:recover-known-failure",
                )
            )
            return self._fail(transaction, exc.code, exc.message)
        return self._capture_confirmed_order(transaction, order.order_id)

    async def _recover_ambiguous_completion(
        self, transaction: AgentTransaction
    ) -> AgentTransaction:
        if transaction.checkout is None or transaction.payment_id is None:
            raise RuntimeError("Recovery requires checkout and payment references")
        checkout = transaction.checkout
        payment_id = transaction.payment_id
        transaction = self._transition(
            transaction,
            TransactionState.RECOVERY_REQUIRED,
            "Merchant response was lost; reconciling by checkout ID before retry.",
        )
        try:
            order = await self.merchant.get_order_by_checkout(checkout.checkout_id)
        except CommerceError as exc:
            if exc.code != "NOT_FOUND":
                raise
            self.payments.recover_authorization(
                RecoverAuthorizationRequest(
                    payment_id=payment_id,
                    reconciled_order_id=None,
                    idempotency_key=f"{transaction.transaction_id}:recovery-no-order",
                )
            )
            return self._fail(
                transaction,
                "ORDER_NOT_CREATED",
                "No merchant order exists; payment authorization was voided.",
            )
        self.payments.recover_authorization(
            RecoverAuthorizationRequest(
                payment_id=payment_id,
                reconciled_order_id=order.order_id,
                idempotency_key=f"{transaction.transaction_id}:recovery-existing-order",
            )
        )
        transaction = self._transition(
            transaction,
            TransactionState.ORDER_CONFIRMED,
            "Reconciliation found the merchant order.",
            updates={"order_id": order.order_id},
        )
        transaction = self._transition(
            transaction,
            TransactionState.PAYMENT_CAPTURED,
            "Existing order payment was captured during recovery.",
        )
        return self._transition(
            transaction,
            TransactionState.FULFILLING,
            "Order is awaiting fulfillment.",
        )

    def _capture_confirmed_order(
        self, transaction: AgentTransaction, order_id: str
    ) -> AgentTransaction:
        if transaction.payment_id is None:
            raise RuntimeError("Confirmed transaction is missing payment ID")
        payment_id = transaction.payment_id
        transaction = self._transition(
            transaction,
            TransactionState.ORDER_CONFIRMED,
            "Merchant returned authoritative order confirmation.",
            updates={"order_id": order_id},
        )
        self.payments.capture(
            CapturePaymentRequest(
                payment_id=payment_id,
                order_id=order_id,
                idempotency_key=f"{transaction.transaction_id}:capture",
            )
        )
        transaction = self._transition(
            transaction,
            TransactionState.PAYMENT_CAPTURED,
            "Authorized payment was captured for the confirmed order.",
        )
        return self._transition(
            transaction,
            TransactionState.FULFILLING,
            "Order is awaiting fulfillment.",
        )

    def _transition(
        self,
        transaction: AgentTransaction,
        state: TransactionState,
        reason: str,
        updates: dict[str, object] | None = None,
    ) -> AgentTransaction:
        updated = transition(
            transaction,
            state,
            reason=reason,
            clock=self._now,
            updates=updates,
        )
        self.repository.save(updated)
        self.audit.record(
            transaction_id=updated.transaction_id,
            action="agent.transaction_transition",
            actor_type="agent",
            actor_id=updated.agent_id,
            subject_type="agent_transaction",
            subject_id=updated.transaction_id,
            data={
                "from_state": transaction.state,
                "to_state": state,
                "reason": reason,
            },
        )
        status = ActivityStatus.COMPLETED
        if state is TransactionState.APPROVAL_PENDING:
            status = ActivityStatus.WAITING
        elif state in {TransactionState.NO_MATCH, TransactionState.REFUNDED}:
            status = ActivityStatus.SUCCEEDED
        elif state is TransactionState.FAILED:
            status = ActivityStatus.FAILED
        self.activities.record(
            transaction_id=updated.transaction_id,
            kind="transaction.transition",
            phase=STATE_PHASES[state],
            status=status,
            title=state.value.replace("_", " ").title(),
            message=reason,
            actor_type="agent",
            actor_id=updated.agent_id,
            authority="orchestrator",
            data={
                "from_state": transaction.state,
                "to_state": state,
            },
        )
        return updated

    def _fail(self, transaction: AgentTransaction, code: str, message: str) -> AgentTransaction:
        if transaction.state is TransactionState.FAILED:
            return transaction
        return self._transition(
            transaction,
            TransactionState.FAILED,
            message,
            updates={"last_error_code": code, "last_error_message": message},
        )

    def _cache_start(
        self,
        request: StartPurchaseRequest,
        fingerprint: str,
        transaction: AgentTransaction,
    ) -> AgentTransaction:
        self.repository.save_idempotent(
            "start_purchase", request.idempotency_key, fingerprint, transaction
        )
        return transaction

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise RuntimeError("Orchestrator clock must return a timezone-aware datetime")
        return value

    @staticmethod
    def _fingerprint(request: BaseModel) -> str:
        canonical = request.model_dump_json(exclude={"idempotency_key"})
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _expect_type(value: object, expected: type[ModelT]) -> ModelT:
        if not isinstance(value, expected):
            raise RuntimeError(f"Corrupt idempotency record: expected {expected.__name__}")
        return value
