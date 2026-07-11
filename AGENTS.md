# Project instructions for Codex

These instructions apply to the entire repository.

## Required context

Before implementing or reviewing work, read:

- `README.md`
- `docs/solution-architecture.md`
- `docs/technology-stack.md`
- `docs/shared-contracts.md`
- `docs/team-playbook.md`
- `docs/workstream-status.md`

Treat those documents as the shared source of truth. If implementation and documentation disagree, stop and surface the disagreement instead of silently inventing a third contract.

## Product boundary

This is an agent-first commerce transaction workflow, not a product-recommendation chatbot and not a large storefront. The mocked shop exists to prove a reusable flow:

```text
discover -> decide -> approve -> purchase -> track -> resolve
```

Optimize work for the canonical end-to-end demo before adding breadth.

## Architectural rules

- Keep agent orchestration, merchant commerce, consent/policy, payments, and presentation as separate boundaries.
- The LLM may choose and explain actions but must not enforce monetary calculations, spending rules, authorization, idempotency, or transaction state.
- Do not expose reusable payment credentials, secrets, authorization headers, or raw card data to prompts, tool results, logs, or the frontend.
- Represent monetary values as integer minor units plus an ISO currency code. Never use floating-point money.
- Every mutation must accept an idempotency key and return the authoritative current resource state.
- Approval must reference an exact checkout ID, checkout version, total, currency, merchant, and expiration.
- A material checkout change invalidates the old approval. Material changes include merchant, line item, quantity, total, currency, fulfillment promise, and return terms.
- Do not report a purchase as successful until an authoritative order confirmation exists.
- On an ambiguous timeout, retrieve current state before retrying a mutation.
- Persist correlation IDs across agent, merchant, payment, and order events.
- Prefer explicit state machines and typed structured results over inferred state from chat text.

## Required implementation stack

- Use Python 3.12 and manage the project with `uv`, `pyproject.toml`, and a committed `uv.lock`.
- Implement backend HTTP APIs with FastAPI and Pydantic v2 models.
- Use the OpenAI Agents SDK for the commerce agent and its tracing. Keep one primary agent unless a demonstrated scenario requires another.
- Implement the merchant-facing MCP surface with the official `mcp` Python package and FastMCP using Streamable HTTP.
- Use SQLAlchemy 2 repositories and Alembic migrations. Default local/demo storage is SQLite in WAL mode behind a configurable `DATABASE_URL`.
- Implement the demo UI in Streamlit. It communicates with the backend API and does not import backend repositories or mutate the database directly.
- Use HTTPX for service/API clients and Pytest for tests. Use Ruff for lint/format and mypy for type checking.
- Use `pydantic-settings` for configuration. Secrets belong in environment variables or an untracked `.env`, never in committed files.

Do not add Redis, Celery, Kafka, Docker as a local prerequisite, a second backend framework, a frontend Node build, or another agent framework without a documented cross-team decision. The hackathon baseline is a modular monolith with one backend process, one Streamlit process, and one SQLite database.

Both REST endpoints and MCP tools must call the same application services. Do not duplicate checkout, payment, approval, or order logic inside transport handlers.

When the project is scaffolded, use the commands recorded in `docs/technology-stack.md`; update that document and this file if the canonical commands change.

## Shared-contract changes

Files or types implementing the objects and operations described in `docs/shared-contracts.md` are cross-team interfaces.

Before changing one:

1. Explain the problem the change solves.
2. Identify affected owners.
3. Update the shared documentation in the same change.
4. Preserve compatibility or coordinate the consumer updates.
5. Add or update a contract/integration test.

Do not rename fields, states, events, or tool semantics as an incidental refactor.

Update `docs/workstream-status.md` when starting a substantial work item, changing a shared interface, becoming blocked, or handing work to another teammate. Keep it concise and operational; architecture belongs in the other documents.

## Ownership

- Agent/orchestration owner: intent, planning, tool sequencing, recovery, state-machine coordination.
- Commerce/MCP owner: catalog, offers, inventory, checkout, orders, cancellation, returns, MCP interface.
- Payments/trust owner: mandates, approval, scoped credentials, authorize/capture/void/refund, audit evidence.
- Experience/integration owner: user intent UI, approval UI, timeline, demo controls, end-to-end integration.

Ownership is responsibility, not exclusivity. Cross-boundary changes require the relevant owner to review the contract impact.

## Testing expectations

Prioritize tests for business invariants and failure recovery:

- Valid happy-path purchase.
- Offer or price change after approval requires reapproval.
- Out-of-stock item cannot complete checkout.
- Payment decline cannot create a paid order.
- Duplicate mutation with the same idempotency key cannot duplicate an order, capture, cancellation, return, or refund.
- Authorization followed by order failure is voided or moves to an explicit recoverable state.
- An ambiguous timeout is reconciled before retry.
- Cancellation eligibility changes after fulfillment begins.
- Return and refund states remain traceable to the original order and payment.

Run the smallest relevant tests while iterating and the canonical end-to-end flow before handing off.

## Scope discipline

Prefer a reliable vertical transaction over:

- A large catalog.
- Many merchants with shallow behavior.
- Multiple cooperating agents without a demonstrated need.
- UI scraping when structured merchant tools are available.
- Implementing several payment protocols at once.
- Cosmetic features that do not improve the judged transaction flow.
