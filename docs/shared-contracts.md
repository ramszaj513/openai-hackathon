# Shared contracts

This document defines the conceptual cross-team contracts. Exact language types and transport schemas should implement these semantics without silent reinterpretation.

## 1. Common conventions

### Identifiers

Every durable entity has a globally unique opaque ID. Do not derive authority from display names or client-provided IDs.

Common identifiers include:

- `transaction_id`
- `user_id`
- `agent_id`
- `merchant_id`
- `offer_id`
- `checkout_id`
- `approval_id`
- `payment_authorization_id`
- `payment_id`
- `order_id`
- `return_id`
- `refund_id`
- `correlation_id`

### Money

Money is always:

- `amount_minor`: integer minor units, such as grosz.
- `currency`: uppercase ISO 4217 code, such as `PLN`.

All totals must expose their breakdown: subtotal, discount, shipping, tax, fees, and total.

### Time

- Use UTC timestamps in ISO 8601 format at service boundaries.
- Expiring objects expose `expires_at`.
- User-facing code localizes times; domain services do not store local display strings.

### Versioning

Mutable authoritative resources expose an integer `version` that increases on material change. Approvals reference a specific checkout version.

### Idempotency

Every mutation accepts `idempotency_key`.

- Same key and same normalized request returns the original result.
- Same key with different request data returns an idempotency-conflict error.
- Keys are scoped to the operation and acting principal.

### Errors

Operations return stable machine-readable error categories plus safe human-readable context. Minimum categories:

- `VALIDATION_ERROR`
- `NOT_FOUND`
- `CONFLICT`
- `STALE_VERSION`
- `EXPIRED`
- `OUT_OF_STOCK`
- `PRICE_CHANGED`
- `APPROVAL_REQUIRED`
- `APPROVAL_INVALID`
- `PAYMENT_DECLINED`
- `NOT_CANCELLABLE`
- `NOT_RETURNABLE`
- `IDEMPOTENCY_CONFLICT`
- `TEMPORARILY_UNAVAILABLE`
- `RECOVERY_REQUIRED`

## 2. Core domain objects

### PurchaseIntent

Represents the normalized user objective, not payment authority.

Required semantics:

- Original user request.
- Hard constraints.
- Soft preferences.
- Budget and currency.
- Delivery destination reference and deadline.
- Required compatibility and return conditions.
- Allowed substitutions or merchants, if specified.
- Confidence/clarification status.

### SpendingMandate

Represents reusable but limited authority granted by the user.

Required semantics:

- User and agent identity.
- Permitted merchant/category scope.
- Per-transaction and optional cumulative spending limit.
- Currency.
- Required product, delivery, and return constraints.
- Whether final checkout confirmation is required.
- Validity window.
- Revocation status.
- Reserved and captured cumulative spend, so concurrent approvals cannot exceed the limit.

### Offer

Represents a merchant's current proposition for a purchasable product.

Required semantics:

- Merchant and offer identity.
- Product, variant, and compatibility attributes.
- Unit price and currency.
- Available quantity.
- Delivery options or availability hints.
- Return and warranty summary.
- Offer version and expiry.

An offer is not a completed checkout. Tax, shipping, reservation, and final terms remain merchant-authoritative at checkout.

### Checkout

Represents the merchant-authoritative proposed transaction.

Required semantics:

- Checkout ID and version.
- Merchant.
- Line items with offer references and quantities.
- Full money breakdown and total.
- Selected and available fulfillment options.
- Delivery address reference.
- Delivery promise.
- Return/cancellation terms.
- Inventory reservation and checkout expiry.
- Current checkout state.
- Supported payment capabilities.

### CheckoutProposal

Represents the user-facing immutable snapshot requesting authorization.

Required semantics:

- Transaction, checkout, and checkout version.
- Exact merchant, items, totals, currency, fulfillment, and terms.
- Agent's selection explanation and disclosed compromises.
- Constraints satisfied or violated.
- Proposal creation and expiry.
- Content hash or equivalent immutable binding.

### Approval

Represents user authorization for one exact checkout proposal.

Required semantics:

- Approving user.
- Checkout ID, checkout version, and proposal binding.
- Merchant, exact total, and currency.
- Approval method and timestamp.
- Expiry and revocation state.
- Optional reference to a covering spending mandate.
- Immutable checkout-proposal hash used by the approval UI and trust service.

### PaymentAuthorization

Represents reserved ability to charge, not proof of a captured payment.

Required semantics:

- Checkout and approval reference.
- Merchant.
- Authorized amount and currency.
- Status: pending, authorized, declined, voided, expired, or capture-required.
- Expiry.
- Provider reference safe for application use.
- Originating approval and single-use credential references.
- Safe provider error and decline codes when authorization fails; never raw provider messages.

The internal payment lifecycle distinguishes credential issuance, authorization, capture, void, partial/full refund, and reconciliation. The merchant only receives the scoped `PaymentAuthorizationReference`; provider credentials remain inside the payment service.

For interactive Stripe test-mode entry, Stripe Elements owns the card fields and returns an opaque
PaymentMethod identifier to the browser. The explicit approval request may carry that validated
`pm_...` identifier directly to the payment service for one authorization attempt. It must not be
stored in the transaction projection, audit events, model context, or browser conversation history.
Raw card fields never enter an application request.

### PaymentReceipt

Represents the authoritative money result.

Required semantics:

- Payment authorization and order references.
- Authorized, captured, voided, and refunded amounts.
- Currency.
- Provider status and safe reference.
- Timestamp.

### Order

Required semantics:

- Merchant order ID.
- Checkout and transaction references.
- Current order state.
- Confirmed items and totals.
- Fulfillment status and tracking information.
- Cancellation eligibility.
- Return eligibility.
- Creation and update timestamps.

### Return and Refund

Required semantics:

- Original order and payment references.
- Items and quantities.
- Reason.
- Eligibility result.
- Return method and status.
- Refund amount, currency, and status.

Refund status is `PENDING`, `COMPLETED`, or `FAILED`. Provider acceptance is not completion: a
pending refund remains pending until authoritative provider state confirms it, and mandate spend is
restored only for a completed refund. Adding pending and failed states preserves the existing
completed result while allowing asynchronous payment rails to report their state truthfully.

## 3. MCP commerce surface

Tool names may receive a project namespace, but their semantics should remain stable.

### Read-only tools

| Tool | Purpose |
|---|---|
| `search_offers` | Find structured offers satisfying supplied search constraints |
| `get_offer` | Retrieve current offer details and version |
| `get_delivery_options` | Retrieve delivery choices for an offer or checkout context |
| `get_return_policy` | Retrieve machine-readable return conditions |
| `get_checkout` | Retrieve authoritative checkout state and version |
| `get_order` | Retrieve authoritative order and fulfillment state |
| `get_order_by_checkout` | Reconcile ambiguous checkout completion without creating a duplicate |
| `get_refund_status` | Retrieve refund progression |
| `list_transaction_events` | Retrieve merchant transaction events for audit and UI projection |

### Mutating tools

| Tool | Purpose |
|---|---|
| `create_checkout` | Create a merchant checkout from selected offer references |
| `update_checkout` | Change quantity, fulfillment, or address using optimistic version control |
| `cancel_checkout` | Release an unused checkout and inventory reservation |
| `complete_checkout` | Atomically validate checkout/payment authority and create or return the order |
| `cancel_order` | Request cancellation under current merchant rules |
| `create_return` | Create a return for eligible order items |

Payment and user approval should not be casually embedded in merchant discovery tools. Whether payment operations are exposed through MCP or an internal application boundary, they retain the same approval and scoping requirements.

## 4. Operation rules

### `search_offers`

- May return zero or more offers and an explanation of filters applied.
- Does not claim final tax, shipping, or inventory reservation.
- Results include offer version and expiry.
- Product queries and categories are open vocabulary; merchant adapters must not assume a fixed
  product taxonomy.
- At the MCP boundary, dynamic attribute filters use a portable list of `{name, value}` objects;
  the merchant adapter converts that list into its native search representation.

### `create_checkout`

- Merchant recalculates all prices and validates stock.
- Creates a temporary inventory reservation where supported.
- Returns the complete authoritative checkout.
- Does not charge or authorize payment.

### `update_checkout`

- Requires expected checkout version.
- Returns `STALE_VERSION` on concurrent modification.
- Increments version on material change.
- Makes prior approval invalid when the change is material.

### `complete_checkout`

- Requires idempotency key.
- Requires current checkout version.
- Requires valid approval evidence and a matching payment authorization reference.
- Revalidates checkout expiry, stock, total, merchant, amount, and currency.
- Returns the already-created order for a repeated identical request.
- Never returns success without an authoritative order ID.

### `cancel_order`

- Requires idempotency key.
- Returns current order if cancellation was already completed.
- Applies current fulfillment-based eligibility.
- Triggers void or refund workflow according to payment state.

### `create_return`

- Requires idempotency key.
- Validates item, quantity, return window, and order state.
- Returns the return record and next required action.

## 5. Cross-component events

Minimum event envelope:

- `event_id`
- `event_type`
- `occurred_at`
- `correlation_id`
- `transaction_id`
- `subject_type`
- `subject_id`
- `subject_version`
- Safe structured payload

Minimum event types:

- `checkout.created`
- `checkout.updated`
- `checkout.expired`
- `approval.requested`
- `approval.granted`
- `approval.invalidated`
- `payment.authorized`
- `payment.declined`
- `payment.captured`
- `payment.voided`
- `order.confirmed`
- `order.cancelled`
- `order.fulfillment_updated`
- `return.created`
- `return.received`
- `refund.pending`
- `refund.completed`

Consumers must tolerate duplicate event delivery and use `event_id` for deduplication.

## 6. Authoritative ownership

| Data | Authority |
|---|---|
| User request and agent task | Orchestrator |
| Spending mandate and approval validity | Policy/consent engine |
| Product, stock, price, tax, delivery, checkout, order | Merchant |
| Authorization, capture, void, refund | Payment provider through payment adapter |
| User-facing timeline | Projection derived from authoritative events/state |

No component may overwrite another component's authoritative state based only on model output or UI state.

## 7. Agent transaction projection

The orchestration layer exposes one `AgentTransaction` projection for the UI and recovery logic. It contains:

- Normalized user intent and clarification questions.
- Selected offer, confidence, reasoning, rejected offers, and compromises.
- Exactly four agent-selected display parameters (`label` and `value`) explaining the successful
  match; presentation clients render these values without deriving meaning from attribute keys.
- Current deterministic transaction state and complete transition history.
- Checkout proposal and approval/payment/order/return references.
- Processed merchant event IDs.
- Stable failure code and safe explanation when execution stops.

The projection is not authoritative for merchant checkout/order or provider payment state; it references those authoritative resources.

### Transaction activity projection

The orchestration API also exposes an append-only activity projection for live user interfaces.
Every item has a transaction-scoped sequence, stable event ID, phase, status, safe title/message,
actor, authority, timestamp, and non-sensitive structured data. Consumers resume with
`after_sequence` or SSE `Last-Event-ID` and must render the transaction snapshot before applying
new activity. Activity is explanatory; deterministic transaction state remains authoritative.

## 8. Contract acceptance scenarios

Before a cross-team interface is considered stable, verify:

1. Happy path returns the same checkout/order on identical idempotent retry.
2. Changed price increments checkout version and invalidates approval.
3. Expired checkout cannot be completed.
4. Mismatched amount, currency, merchant, or checkout rejects payment authority.
5. Order timeout can be reconciled by retrieving order/checkout state.
6. Cancellation produces a void or refund according to capture state.
7. Return and refund remain linked to the original items, order, and payment.
