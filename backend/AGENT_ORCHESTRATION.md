# Agent orchestration workstream

Owner: **Maciej**

This workstream owns the agent-first transaction lifecycle. The model interprets intent and performs read-only offer discovery; deterministic services enforce checkout, approval, payment, order, and recovery state.

## Implemented capabilities

- Structured purchase-intent normalization.
- Clarification state with explicit missing fields and questions.
- Deterministic offline interpreter for development and CI.
- OpenAI Agents SDK interpreter with Pydantic structured output.
- Read-only OpenAI offer planner connected to merchant MCP tools.
- Deterministic offer planner enforcing hard constraints and explaining rejection reasons.
- Explicit transaction state machine from intent through refund.
- Merchant access through a typed MCP gateway.
- Exact checkout proposal and policy evaluation.
- Explicit approval or mandate-based autonomous execution.
- Single-use payment authorization followed by merchant order and capture.
- Payment-decline handling without order creation.
- Ambiguous completion reconciliation by checkout ID.
- Event-driven resumption for fulfillment and delivery.
- Cancellation, return, and refund orchestration.
- Agent decision/state audit entries correlated by transaction ID.
- REST endpoints under `/api/agent` for the Streamlit integration.

## Agent versus deterministic responsibilities

### Model-controlled

- Interpret the user's desired outcome into a structured purchase intent.
- Discover merchant offers through read-only MCP tools.
- Compare eligible offers and explain the decision and compromises.
- Produce confidence and clarification questions.

### Deterministic services

- Recalculate and version checkout.
- Decide whether approval is valid or required.
- Enforce spending mandates.
- Issue and consume payment credentials.
- Authorize, capture, void, and refund money.
- Create and reconcile merchant orders.
- Enforce transaction state transitions and idempotency.

The offer-planning agent can access only:

```text
search_offers
get_offer
get_delivery_options
get_return_policy
```

It cannot call checkout completion or payment tools.

## Runtime modes

### Production/demo agent mode

```text
AGENT_USE_OPENAI=1
AGENT_USE_MCP=1
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-sol
OPENAI_REASONING_EFFORT=high
MCP_BASE_URL=http://127.0.0.1:8000/mcp
```

This uses the OpenAI Agents SDK for structured intent and read-only MCP offer planning. Sensitive trace payloads remain disabled by the project environment settings.

### Model-disabled infrastructure mode

```text
AGENT_USE_OPENAI=0
AGENT_USE_MCP=0
```

This keeps commerce, trust, payment, REST, and direct merchant infrastructure available without
pretending to understand natural language. Starting an agent transaction returns a clear model
configuration error. Tests inject already-structured intents instead of maintaining a second
keyword-based parser.

### MCP without model calls

```text
AGENT_USE_OPENAI=0
AGENT_USE_MCP=1
```

This mode is useful for verifying the normalized merchant protocol independently of model behavior;
it does not interpret user purchase requests.

## Transaction states

```text
INTENT_CAPTURED
-> CLARIFICATION_REQUIRED or DISCOVERING
-> NO_MATCH (terminal, confident catalog result)
-> OFFER_SELECTED
-> CHECKOUT_DRAFT
-> APPROVAL_PENDING
-> APPROVED
-> PAYMENT_AUTHORIZING
-> PAYMENT_AUTHORIZED
-> ORDER_COMMITTING
-> ORDER_CONFIRMED or RECOVERY_REQUIRED
-> PAYMENT_CAPTURED
-> FULFILLING
-> DELIVERED
-> RETURN_REQUESTED / CANCELLATION_REQUESTED
-> REFUND_PENDING
-> REFUNDED
```

Any invalid or unrecoverable path ends in `FAILED` with a stable error code and explanation.

## Ambiguous completion recovery

If `complete_checkout` times out, the agent must not retry blindly:

1. Move to `RECOVERY_REQUIRED`.
2. Query the merchant using `get_order_by_checkout`.
3. If an order exists, capture the existing authorization once.
4. If no order exists, void the orphan authorization and invalidate the approval.

Both paths are covered by automated tests.

## REST handoff for Bartosz

```text
POST /api/agent/transactions                                  -> 202 receipt
GET  /api/agent/transactions/{transaction_id}
GET  /api/agent/transactions/{transaction_id}/activity?after_sequence=N
GET  /api/agent/transactions/{transaction_id}/stream          -> SSE
POST /api/agent/transactions/{transaction_id}/approve
POST /api/agent/transactions/{transaction_id}/resume
POST /api/agent/transactions/{transaction_id}/cancel
POST /api/agent/transactions/{transaction_id}/return
```

The create response immediately contains the `INTENT_CAPTURED` transaction plus status, activity,
and stream URLs. Model and MCP processing continues as a background task. `AgentTransaction`
contains intent, selection explanation, checkout proposal, references, current state, errors, and
the complete deterministic transition timeline.

The activity endpoint is an append-only, safe UI projection with monotonically increasing sequence
numbers. It includes transaction transitions, model-call boundaries, MCP tool-call boundaries, and
structured selection summaries. It deliberately excludes prompts, raw model output, chain-of-thought,
payment credentials, and sensitive tool payloads. SSE emits `transaction.activity` events and accepts
the standard `Last-Event-ID` header for reconnection; polling with `after_sequence` is the fallback.

## Verification

```text
uv run pytest backend/tests/unit/test_orchestration_service.py
uv run pytest backend/tests/integration/test_agent_mcp_integration.py
uv run pytest backend/tests/integration/test_commerce_api.py
uv run ruff check backend
uv run mypy backend/src
```

Live OpenAI execution is intentionally separate from deterministic automated tests and requires `OPENAI_API_KEY` plus `OPENAI_MODEL`.

