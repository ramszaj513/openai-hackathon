# Agent Commerce Gateway

An agent-first transaction workflow for the Boski agentic-commerce hackathon.

The project demonstrates how an AI agent can move from a natural-language buying intent to a completed and managed order while keeping the user in control:

```text
discover -> decide -> approve -> purchase -> track -> resolve
```

The mocked shop is a demonstration merchant, not the product. The product is the reusable transaction layer connecting an agent, merchant capabilities, consent policy, payments, and post-purchase operations.

## Start here

Every contributor and every Codex task should read these documents before making changes:

1. [Solution architecture](docs/solution-architecture.md)
2. [Python technology stack](docs/technology-stack.md)
3. [Shared contracts](docs/shared-contracts.md)
4. [Team playbook](docs/team-playbook.md)
5. [Live workstream status](docs/workstream-status.md)
6. [Codex project instructions](AGENTS.md)

The original challenge presentation is available at [resources/boski-case.pdf](resources/boski-case.pdf).

## Canonical demo scenario

> Buy a Mac-compatible monitor for no more than 1,200 PLN, deliverable tomorrow, with at least a 30-day return window. Buy it if you are confident.

The complete demo should show:

1. Constraint extraction and structured offer discovery.
2. Deterministic rejection of invalid offers.
3. A versioned checkout proposal with the exact total and terms.
4. Explicit approval or approval under a preconfigured mandate.
5. Scoped payment authorization, order creation, capture, and receipt.
6. Order monitoring and one post-purchase exception.
7. Cancellation or return followed by refund tracking.

## Repository areas

```text
backend/    Python FastAPI application, domain modules, MCP server, and tests
frontend/   React/TypeScript single-chat approval, timeline, and demo application
docs/       Architecture, stack, contracts, and team working agreement
resources/  Hackathon source materials and deterministic seed inputs
```

The implementation structure inside `backend/` and `frontend/` may evolve, but the domain boundaries and invariants in `docs/` are the team contract.

## Product principles

- The agent is the primary operator; the UI is the approval and observability surface.
- The model proposes actions; deterministic services enforce money, policy, and state transitions.
- Approval is bound to an exact, immutable checkout version.
- Payment credentials never enter model context.
- Every mutating operation is idempotent and auditable.
- Purchase success means a confirmed order, not a successful tool call or payment attempt.
- The workflow continues after checkout through tracking, cancellation, return, and refund.

## Technology summary

- Python 3.12 managed with `uv` and a committed lockfile.
- FastAPI, Uvicorn, Pydantic v2, and `pydantic-settings` for the backend.
- OpenAI Agents SDK for the single commerce agent, tool orchestration, and tracing.
- Official MCP Python SDK with FastMCP and Streamable HTTP for merchant tools.
- SQLAlchemy 2 and Alembic, using SQLite in WAL mode for the hackathon demo.
- React, TypeScript, and Vite for the single-chat intent, approval, and transaction timeline UI.
- Pytest, HTTPX, Ruff, and mypy for verification.

See [Python technology stack](docs/technology-stack.md) for the decisions, boundaries, and planned layout.

## Payment rails

The deterministic simulator remains the default. To exercise real provider semantics in Stripe
test mode, copy `.env.example` to the ignored `.env`, set `PAYMENT_PROVIDER=stripe`, and provide a
`STRIPE_SECRET_KEY` beginning with `sk_test_`. The integration uses card PaymentIntents with manual
capture, so funds are authorized only after exact checkout approval and captured only after the
merchant confirms an order. Live-mode Stripe keys are intentionally rejected.
