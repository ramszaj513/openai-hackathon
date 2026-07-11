"""Explicit transaction state machine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from agent_commerce.commerce.errors import conflict
from agent_commerce.orchestration.models import (
    AgentTransaction,
    TransactionState,
    TransitionRecord,
)

ALLOWED_TRANSITIONS: dict[TransactionState, set[TransactionState]] = {
    TransactionState.INTENT_CAPTURED: {
        TransactionState.CLARIFICATION_REQUIRED,
        TransactionState.DISCOVERING,
        TransactionState.FAILED,
    },
    TransactionState.CLARIFICATION_REQUIRED: {
        TransactionState.INTENT_CAPTURED,
        TransactionState.FAILED,
    },
    TransactionState.DISCOVERING: {
        TransactionState.NO_MATCH,
        TransactionState.OFFER_SELECTED,
        TransactionState.FAILED,
    },
    TransactionState.NO_MATCH: set(),
    TransactionState.OFFER_SELECTED: {
        TransactionState.CHECKOUT_DRAFT,
        TransactionState.FAILED,
    },
    TransactionState.CHECKOUT_DRAFT: {
        TransactionState.APPROVAL_PENDING,
        TransactionState.FAILED,
    },
    TransactionState.APPROVAL_PENDING: {
        TransactionState.APPROVED,
        TransactionState.FAILED,
    },
    TransactionState.APPROVED: {
        TransactionState.PAYMENT_AUTHORIZING,
        TransactionState.FAILED,
    },
    TransactionState.PAYMENT_AUTHORIZING: {
        TransactionState.PAYMENT_AUTHORIZED,
        TransactionState.FAILED,
    },
    TransactionState.PAYMENT_AUTHORIZED: {
        TransactionState.ORDER_COMMITTING,
        TransactionState.FAILED,
    },
    TransactionState.ORDER_COMMITTING: {
        TransactionState.ORDER_CONFIRMED,
        TransactionState.RECOVERY_REQUIRED,
        TransactionState.FAILED,
    },
    TransactionState.RECOVERY_REQUIRED: {
        TransactionState.ORDER_CONFIRMED,
        TransactionState.FAILED,
    },
    TransactionState.ORDER_CONFIRMED: {
        TransactionState.PAYMENT_CAPTURED,
        TransactionState.FAILED,
    },
    TransactionState.PAYMENT_CAPTURED: {
        TransactionState.FULFILLING,
        TransactionState.REFUND_PENDING,
        TransactionState.FAILED,
    },
    TransactionState.FULFILLING: {
        TransactionState.DELIVERED,
        TransactionState.CANCELLATION_REQUESTED,
        TransactionState.FAILED,
    },
    TransactionState.DELIVERED: {
        TransactionState.RETURN_REQUESTED,
        TransactionState.FAILED,
    },
    TransactionState.CANCELLATION_REQUESTED: {
        TransactionState.CANCELLED,
        TransactionState.FULFILLING,
        TransactionState.FAILED,
    },
    TransactionState.CANCELLED: {
        TransactionState.REFUND_PENDING,
        TransactionState.REFUNDED,
    },
    TransactionState.RETURN_REQUESTED: {
        TransactionState.REFUND_PENDING,
        TransactionState.FAILED,
    },
    TransactionState.REFUND_PENDING: {
        TransactionState.REFUNDED,
        TransactionState.FAILED,
    },
    TransactionState.REFUNDED: set(),
    TransactionState.FAILED: set(),
}


def transition(
    transaction: AgentTransaction,
    to_state: TransactionState,
    *,
    reason: str,
    clock: Callable[[], datetime],
    updates: dict[str, object] | None = None,
) -> AgentTransaction:
    allowed = ALLOWED_TRANSITIONS[transaction.state]
    if to_state not in allowed:
        raise conflict(
            "Invalid transaction state transition",
            transaction_id=transaction.transaction_id,
            from_state=transaction.state,
            to_state=to_state,
        )
    now = clock()
    record = TransitionRecord(
        from_state=transaction.state,
        to_state=to_state,
        occurred_at=now,
        reason=reason,
    )
    changes: dict[str, object] = {
        "state": to_state,
        "transitions": (*transaction.transitions, record),
        "updated_at": now,
    }
    if updates:
        changes.update(updates)
    return transaction.model_copy(update=changes)
