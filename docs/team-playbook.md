# Four-person team playbook

## 1. Team objective

Four people are building one transaction flow, not four adjacent prototypes. Each person owns a subsystem, while the canonical demo and shared contracts belong to the whole team.

The first priority is always a working vertical slice:

```text
user intent -> offer -> checkout -> approval -> payment -> order -> status
```

After that is reliable, add reapproval and post-purchase resolution.

## 2. Ownership map

### Maciej: Agent and orchestration

Owns:

- Purchase-intent normalization.
- Clarification behavior.
- Tool selection and sequencing.
- Transaction-state coordination.
- Offer evaluation and explanation.
- Recovery after tool failure or ambiguous timeout.
- Resuming work from order events.

Depends on:

- MCP tool schemas from Kuba.
- Approval and payment contracts from Piotr.
- UI event and state requirements from Bartosz.

Must deliver:

- Canonical tool-call flow.
- Explicit state transitions.
- No success claim without an order confirmation.
- Happy-path and failure-recovery orchestration tests.

### Kuba: Commerce and MCP

Owns:

- Mock catalog and offers.
- Compatibility attributes.
- Inventory and reservation.
- Cart/checkout calculations and versioning.
- Delivery and return rules.
- Orders, cancellation, returns, and merchant events.
- MCP server and commerce tool schemas.

Depends on:

- Constraint/search needs from Maciej.
- Payment completion contract from Piotr.
- Timeline/event needs from Bartosz.

Must deliver:

- Deterministic merchant seed data.
- Read-only and mutation tools described in the shared contract.
- Idempotent checkout/order behavior.
- Demo controls for stock, price, and fulfillment changes.

### Piotr: Payments, trust, and audit

Owns:

- Spending mandates.
- Checkout proposals and approval evidence.
- Approval validation and invalidation.
- Payment adapter.
- Authorization, capture, decline, void, and refund.
- Financial idempotency.
- Transaction audit evidence.

Depends on:

- Checkout/version truth from Kuba.
- Orchestration timing from Maciej.
- Approval and receipt presentation requirements from Bartosz.

Must deliver:

- Deterministic payment simulator first.
- Exact approval binding.
- Safe payment references without secrets.
- Recovery for authorized-payment/order-creation failure.

### Bartosz: Experience, integration, and demo

Owns:

- User-intent interface.
- Extracted-constraints display.
- Agent activity and transaction timeline.
- Checkout proposal and approval UI.
- Payment receipt and order status UI.
- Exception-resolution UI.
- Canonical end-to-end test and demo controls.
- Presentation flow and backup demo path.

Depends on:

- Structured transaction state and explanations from Maciej.
- Checkout/order data and events from Kuba.
- Approval/payment/receipt data from Piotr.

Must deliver:

- One understandable continuous transaction story.
- Clear distinction between proposed, approved, paid, and ordered.
- Reliable reset into known demo data.
- Visible post-purchase resolution.

## 3. Cross-review pairs

- Maciej reviews whether Kuba's MCP tools are sufficient and unambiguous for an agent.
- Kuba reviews whether Maciej assumes merchant facts that tools do not guarantee.
- Piotr reviews every consequential action and every checkout-completion path.
- Bartosz reviews whether the transaction and approval states are understandable to a judge.
- Maciej reviews whether the UI accurately reflects the agent's real state.
- Piotr reviews whether the approval UI binds the exact transaction rather than asking for vague consent.

## 4. First team session

Before splitting work, all four people should agree on:

1. Canonical monitor purchase request.
2. Expected valid and invalid offers.
3. Checkout fields and money breakdown.
4. Approval object and invalidation conditions.
5. Payment states.
6. Order and return states.
7. MCP tool list.
8. Happy-path sequence.
9. Price-change/reapproval sequence.
10. Delay/cancellation/refund sequence.

Any unresolved item should be written as an explicit open decision rather than hidden in one person's code.

## 5. Delivery milestones

### Milestone 1: Walking skeleton

Target: first 20–25% of available hackathon time.

Required:

- User submits canonical request.
- Agent calls a search tool.
- Merchant returns at least one offer.
- Agent creates checkout.
- User approves exact proposal.
- Mock payment succeeds.
- Merchant returns an order.
- UI shows confirmation.

Quality can be rough, but all component boundaries must connect.

### Milestone 2: Credible transaction

Required:

- Multiple offers and deterministic constraint validation.
- Taxes, shipping, checkout version, and expiry.
- Approval invalidation.
- Authorization and capture distinction.
- Idempotent completion.
- Receipt and audit timeline.

### Milestone 3: Agent value after checkout

Required:

- Order event changes state.
- Agent resumes automatically or from an event trigger.
- Agent proposes a valid remedy.
- Cancellation or return is executed.
- Refund progression is visible.

### Milestone 4: Demo hardening

Required:

- Deterministic reset.
- Failure and loading states.
- Rehearsed timing.
- No manual database edits during demo.
- Backup scenario or recording if hackathon rules allow it.
- No major architectural additions.

## 6. Branch and integration workflow

Suggested short-lived branches:

```text
codex/agent-orchestration
codex/commerce-mcp
codex/payments-trust
codex/experience
```

Working agreement:

- Integrate small changes every 2–3 hours.
- Keep the canonical scenario runnable on the integration branch.
- Do not commit credentials or local secrets.
- Do not make incidental cross-contract renames.
- Pair when changing an interface owned by another subsystem.
- Update documentation and contract tests with shared-contract changes.
- Announce breaking changes before merging, not afterward.

The agreed implementation stack and canonical local commands are defined in `docs/technology-stack.md`. A dependency or framework change is a shared-interface decision because it affects all four local environments.

## 7. Status rhythm

Hold a five-minute synchronization every 60–90 minutes. Each person reports only:

1. Completed.
2. Next deliverable.
3. Current blocker.
4. Shared contract changed or proposed.

The integration owner maintains a visible list of the first broken step in each canonical scenario.

Record the result in `docs/workstream-status.md` so teammates and their local Codex tasks do not depend on ephemeral chat messages.

## 8. Codex usage

Each teammate has Codex Pro and should use focused tasks rather than one all-purpose conversation.

Recommended task separation:

- Implementation task for the owned subsystem.
- Review task for correctness and contract compliance.
- Adversarial/test task for failure scenarios.
- Protocol research task only when current primary documentation is needed.

Every Codex task should be told to read the root `AGENTS.md`. Useful review prompts include:

- Review this change against `docs/shared-contracts.md` and identify contract drift.
- Find a path that could complete checkout without valid current approval.
- Test duplicate and ambiguous-timeout behavior for this mutation.
- Trace the canonical scenario and report the first invalid transition.
- Verify that no reusable payment credential reaches model context, frontend state, or logs.
- Check whether the UI distinguishes authorization, capture, order confirmation, and refund.

Codex may propose shared-contract changes, but a human owner must coordinate the decision with affected teammates.

## 9. Handoff template

When handing work to another person, include:

```text
Outcome:
Changed interfaces:
How to run/verify:
Known limitations:
Expected next consumer action:
```

Do not hand off with only “it is done” or a commit hash.

## 10. Integration checklist

Run this before declaring the demo ready:

- Agent extracts the expected hard constraints.
- Merchant search returns structured offers.
- Invalid offers are rejected for explicit reasons.
- Checkout total comes from the merchant.
- Proposal shows exact version, total, delivery, and return terms.
- Approval references the same checkout version.
- Changed checkout cannot reuse old approval.
- Payment authorization matches merchant, amount, currency, and checkout.
- Repeated completion cannot duplicate order or capture.
- UI waits for authoritative order confirmation.
- Order event updates the transaction timeline.
- Cancellation or return follows current merchant eligibility.
- Void or refund follows payment state.
- All steps share a correlation/transaction ID.
- No secrets appear in agent messages, UI payloads, or logs.
- Demo reset restores deterministic data.

## 11. Scope-cutting order

If time becomes constrained, remove scope in this order:

1. Extra merchants.
2. Additional product categories.
3. A second payment protocol.
4. Advanced recommendation behavior.
5. Decorative UI features.
6. Multi-agent decomposition.

Do not cut exact approval binding, payment idempotency, authoritative order confirmation, or one post-purchase resolution flow. Those are the core of the submission.
