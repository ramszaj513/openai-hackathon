# Commerce and MCP workstream

Owner: **Kuba**

This README covers the commerce/MCP slice. The integrated trust and payment slice is documented in [PAYMENTS_TRUST.md](PAYMENTS_TRUST.md).

The agent transaction layer is documented in [AGENT_ORCHESTRATION.md](AGENT_ORCHESTRATION.md).

This folder contains the merchant-authoritative commerce implementation and its REST/MCP transports. It intentionally does not implement agent reasoning, user approval issuance, payment authorization/capture, or Streamlit UI.

## Implemented capabilities

- Deterministic monitor catalog and structured offer search.
- Offer versions, expiry, stock, delivery options, and return policies.
- Inventory-reserving, expiring, versioned checkouts.
- Quantity and delivery updates with optimistic concurrency.
- Exact approval and payment-authorization binding validation at completion.
- Idempotent order creation, checkout/order cancellation, fulfillment transitions, and returns.
- Merchant domain events including refund requests for the payment owner.
- FastAPI REST routes and FastMCP Streamable HTTP tools over the same service.
- Stable machine-readable commerce errors.

## Ownership boundaries

- Maciej consumes the MCP tools from agent orchestration.
- Piotr creates valid `ApprovalEvidence` and `PaymentAuthorizationReference` objects and consumes `refund.pending` events.
- Bartosz consumes REST endpoints and the transaction event projection.
- The current in-memory repository is deterministic for integration. A SQLAlchemy repository can replace it without changing service or transport contracts.

## Local verification

With the project environment synchronized:

```text
$env:PYTHONPATH="backend/src"   # PowerShell
uv run pytest backend/tests
uv run uvicorn agent_commerce.main:app --reload --app-dir backend/src
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`; REST endpoints are under `/api`.

## Tests

- `tests/unit`: commerce rules, idempotency, expiry, approval binding, cancellation, returns.
- `tests/contract`: FastMCP tool names and structured tool results.
- `tests/integration`: REST behavior and real Streamable HTTP MCP initialization.
