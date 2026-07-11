# Payments, trust, and audit workstream

Owner: **Piotr**

This workstream turns a merchant checkout into a precisely authorized, auditable payment. It is intentionally separate from merchant MCP tools: the shop owns checkout/order truth, while the user's application owns consent and payment authority.

## Implemented capabilities

- Scoped spending mandates with merchant, category, transaction, cumulative, currency, delivery, and return-policy limits.
- Reserved mandate budget at approval time to prevent concurrent overspending.
- Immutable checkout proposals with an exact content hash.
- Explicit user approval and mandate-based auto-approval.
- Approval rejection, expiry, revocation, and automatic invalidation after checkout changes.
- Merchant-compatible `ApprovalEvidence` bound to checkout ID, version, merchant, amount, currency, and expiry.
- Single-use, transaction-scoped payment credentials.
- Provider-neutral payment adapter with a deterministic simulator.
- Opt-in Stripe test-mode card adapter using PaymentIntents with manual capture.
- Authorization, decline, capture, void, partial/full refund, and receipts.
- Idempotency across every consequential trust and payment mutation.
- Recovery that captures an authorization when reconciliation finds an order, or voids it when no order exists.
- Append-only audit events correlated by transaction ID.
- FastAPI routes under `/api/trust` and `/api/payments`.

## Integration boundaries

### Inputs from Kuba's commerce service

- Authoritative `Checkout` and checkout version.
- Merchant, line items/categories, total, delivery, returns, and expiry.
- Confirmed `Order` before capture.
- Checkout update/expiry/cancellation events, which automatically invalidate stale approvals.

### Outputs to the commerce service

- `ApprovalEvidence`.
- `PaymentAuthorizationReference` only after successful authorization.

### Inputs/outputs for Maciej's agent

- Policy decision: denied, explicit approval required, or auto-approved.
- Safe payment status and receipt data.
- No reusable credential or provider secret is exposed to model context.

### Inputs/outputs for Bartosz's UI

- Checkout proposal and content hash.
- Approval actions and policy reasons.
- Payment state, receipts, refunds, recovery result, and audit timeline.

## Core safety properties

- A text statement from the model is never approval.
- Approval is usable only for the exact proposal hash and checkout version.
- Payment authorization cannot exceed or change the approved merchant, amount, or currency.
- One approval cannot have two active/captured payments.
- A credential is short-lived, checkout-scoped, and single-use.
- Capture requires an order ID and the exact authorized amount.
- An orphan authorization is voided after merchant reconciliation.
- Refunds cannot exceed captured funds and restore mandate spend capacity.
- Stripe configuration accepts test keys only; provider client secrets and raw errors never enter
  application models, audit data, the frontend, or model context.
- Stripe mutations receive stable hashed idempotency keys, making an ambiguous transport retry safe.

## Selecting the payment rail

The simulator is the default and requires no external service. For Stripe test mode:

```text
PAYMENT_PROVIDER=stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PAYMENT_METHOD=pm_card_visa
```

`STRIPE_PAYMENT_METHOD` is a server-side test PaymentMethod identifier, not reusable card data.
Use `STRIPE_DECLINE_PAYMENT_METHOD` to configure the deterministic decline scenario. The application
rejects live-mode keys and never returns a Stripe PaymentIntent client secret.

## Verification

```text
$env:PYTHONPATH="backend/src"
uv run pytest backend/tests/unit/test_trust_service.py
uv run pytest backend/tests/unit/test_payment_service.py
uv run pytest backend/tests/integration/test_commerce_api.py
```

The automated suite includes the complete flow:

```text
checkout -> proposal -> approval -> credential -> authorization
-> merchant order -> capture -> receipt -> refund
```
