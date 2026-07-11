# Python technology stack

## 1. Decision

Build the backend as a **Python 3.12 modular monolith** with two local application processes:

- A FastAPI backend for domain logic, orchestration, REST, MCP, events, and persistence.
- A React/TypeScript frontend for a continuous chat containing user intent, approval, transaction timeline, and demo controls.

The baseline must run locally without Docker, Redis, or a hosted database. Backend dependencies use the shared locked Python environment; frontend dependencies use the committed npm lockfile.

## 2. Selected stack

| Concern | Choice | Why |
|---|---|---|
| Runtime | Python 3.12 | Mature support across the selected agent, MCP, web, data, and test libraries |
| Dependency management | `uv`, root `pyproject.toml`, committed `uv.lock` | Fast cross-platform setup and one reproducible environment for four developers |
| HTTP backend | FastAPI + Uvicorn | Typed APIs, generated OpenAPI, async support, and direct Pydantic integration |
| Validation/configuration | Pydantic v2 + `pydantic-settings` | One schema language for API, MCP, domain boundaries, and environment configuration |
| Agent runtime | OpenAI Agents SDK for Python | Tool orchestration, structured outputs, guardrails, sessions, and built-in traces |
| Merchant protocol | Official MCP Python SDK (`mcp`) with FastMCP | Official Tier 1 Python SDK and type-derived tool schemas |
| MCP transport | Streamable HTTP | Current HTTP transport; mount under the backend and avoid a separate tool service |
| Persistence | SQLAlchemy 2 + Alembic | Explicit repository boundary, migrations, and SQLite/PostgreSQL portability |
| Local/demo database | SQLite in WAL mode | Zero infrastructure, deterministic reset, and sufficient concurrency for one backend writer |
| UI | React 19 + TypeScript + Vite | Fine-grained in-chat interaction, responsive layouts, accessible controls, and predictable client state without page-style reruns |
| HTTP client | HTTPX | Async-capable service calls and FastAPI-compatible testing |
| Tests | Pytest + `pytest-asyncio` + HTTPX | Unit, async orchestration, contract, and API tests in one ecosystem |
| Quality | Ruff + mypy | Fast formatting/linting plus type checking across shared contracts |

## 3. Why this is the most productive option

### One language for consequential behavior

All consequential behavior remains in Python: orchestration, commerce, approval, payment, persistence, events, and authoritative state transitions. The TypeScript frontend only renders safe projections and invokes REST operations, so it cannot recalculate totals or manufacture authority.

### One backend, multiple clean interfaces

REST handlers and FastMCP tools are transport adapters over the same application services. This avoids implementing checkout twice and prevents REST and MCP behavior from drifting.

### Minimal local infrastructure

SQLite and an in-process event trigger remove Docker, Redis, Celery, and cloud-database setup from the critical path. The database remains behind SQLAlchemy repositories, so PostgreSQL can replace it through `DATABASE_URL` if deployment requires it.

### Strong agent observability

The OpenAI Agents SDK provides traces for model generations, tools, guardrails, and custom spans. SDK traces help debug agent runs; the application's own audit records remain the authoritative transaction evidence.

### Why the frontend decision changed

The phased Streamlit implementation made a single continuous transaction feel like a sequence of separate screens and reruns. The demo requires approval cards, progress, order controls, and recovery state to remain in one stable conversation. React provides that interaction model while the existing REST boundary keeps all consequential rules in the Python backend. This change affects local setup and the experience/orchestration integration owners, but it does not change any commerce, approval, payment, or order schema.

### FastMCP matches the shared contract

FastMCP derives tool schemas from Python type hints. It should expose structured results while calling the same commerce services used by REST.

## 4. Deliberate exclusions

Do not add these to the baseline:

- Django: more framework surface than the transaction demo needs.
- Flask: less direct typing and schema integration than FastAPI.
- LangChain or another agent framework alongside the OpenAI Agents SDK.
- A separate microservice per domain boundary.
- Redis, Celery, Kafka, or a workflow engine.
- Docker as a requirement for local development.
- PostgreSQL as a requirement for the first demo.
- A second frontend framework or a server-rendered Node application.
- Direct database access from the frontend.
- Both MPP and x402 payment implementations.

Reconsider an exclusion only when a concrete requirement cannot be met by the baseline and record the decision in `workstream-status.md`.

## 5. Planned repository layout

```text
openai-hackathon/
|-- pyproject.toml
|-- uv.lock
|-- .python-version
|-- .env.example
|-- backend/
|   |-- src/
|   |   `-- agent_commerce/
|   |       |-- api/              # FastAPI REST routes and request wiring
|   |       |-- orchestration/    # OpenAI agent, tools, runs, sessions
|   |       |-- commerce/         # Catalog, offers, checkout, orders, returns
|   |       |-- trust/            # Mandates, proposals, approvals, policy
|   |       |-- payments/         # Adapter, simulator, optional Stripe provider
|   |       |-- mcp_server/       # FastMCP transport adapters
|   |       |-- audit/            # Transactions, audit events, projections
|   |       |-- events/           # Persisted events and in-process dispatch
|   |       |-- db/               # SQLAlchemy models, sessions, repositories
|   |       |-- settings.py       # Pydantic settings
|   |       `-- main.py           # ASGI application composition
|   `-- tests/
|       |-- unit/
|       |-- contract/
|       |-- integration/
|       `-- e2e/
|-- frontend/
|   |-- src/
|   |   |-- App.tsx               # Single-chat transaction experience
|   |   |-- components/           # Presentational UI components
|   |   `-- lib/api.ts            # Typed REST-only browser client
|   |-- package.json
|   `-- vite.config.ts
|-- alembic/
|-- docs/
`-- resources/
```

This is one Python project and one lockfile, not a `uv` multi-package workspace. Domain isolation comes from modules and interfaces; separate packages would slow initial integration.

## 6. Runtime boundaries

### FastAPI process

Owns:

- All domain and application services.
- Database sessions and migrations.
- REST endpoints for the React frontend.
- FastMCP Streamable HTTP endpoint for agents and external clients.
- OpenAI agent execution.
- Payment simulator and provider adapters.
- Transaction audit and event dispatch.

### React/Vite process

Owns:

- Rendering and recoverable browser session state.
- Calling REST endpoints through a typed fetch client.
- Polling transaction projections during agent, payment, and order progress.
- Collecting explicit approval and sending it to the backend.

It does not:

- Import SQLAlchemy repositories.
- Recalculate checkout totals.
- Validate approval.
- Call a payment provider directly.
- Store authoritative transaction state.

### MCP boundary

FastMCP tools call commerce application services inside the backend process. The OpenAI agent connects through the MCP Streamable HTTP interface so the demo proves the merchant is independently agent-readable rather than relying on private in-process shortcuts.

Application services may be called directly in unit tests. The canonical end-to-end test must exercise MCP.

## 7. Persistence and events

### SQLite baseline

- Store one database file under a runtime-data directory ignored by Git.
- Enable WAL mode and foreign keys on connection.
- Make the FastAPI process the only database-writing application process.
- Let the React frontend read and mutate state only through REST.
- Use Alembic for schema changes.
- Provide a deterministic reset operation that recreates the catalog, user profile, mandates, and demo scenarios.

### Events

- Persist every domain event in the same database transaction as its state change.
- Use an in-process async queue or dispatcher to wake orchestration logic.
- Deduplicate consumers using `event_id`.
- Let the UI poll a transaction projection instead of depending on a fragile streaming connection.

Do not use only an in-memory queue: persisted events are required for audit and recovery.

## 8. Agent implementation

- Use one OpenAI Agents SDK `Agent` as the commerce orchestrator.
- Use structured Pydantic outputs for intent normalization and other machine-consumed decisions.
- Connect merchant operations through the MCP server.
- Keep approval, payment, totals, version checks, and transaction-state validity in deterministic services.
- Map the SDK trace/group identifier to the project `transaction_id` or `correlation_id` where possible.
- Configure the model through `OPENAI_MODEL`; do not scatter model IDs through code.
- Use the strongest current model available to the team for the final demo, while allowing a cheaper development model without code changes.
- Disable sensitive model/tool payload logging and review trace content before using realistic user or payment data.

The OpenAI Agents SDK directly supports MCP servers and built-in tool tracing. The project uses those capabilities rather than building a custom agent loop unless a missing requirement is demonstrated.

## 9. Configuration

Planned environment settings:

```text
OPENAI_API_KEY
OPENAI_MODEL
OPENAI_TRANSCRIPTION_MODEL=gpt-realtime-whisper
OPENAI_TRANSCRIPTION_LANGUAGE=pl
OPENAI_TRANSCRIPTION_DELAY=low
DATABASE_URL=sqlite:///./runtime/agent-commerce.db
APP_ENV=development
BACKEND_BASE_URL=http://localhost:8000
MCP_BASE_URL=http://localhost:8000/mcp
PAYMENT_PROVIDER=simulator
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_PAYMENT_METHOD=pm_card_visa
STRIPE_DECLINE_PAYMENT_METHOD=pm_card_visa_chargeDeclined
STRIPE_API_BASE=https://api.stripe.com/v1
STRIPE_TIMEOUT_SECONDS=10
OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA=0
OPENAI_AGENTS_DONT_LOG_MODEL_DATA=1
OPENAI_AGENTS_DONT_LOG_TOOL_DATA=1
AGENT_USE_OPENAI=1
AGENT_USE_MCP=1
```

Commit `.env.example`, never `.env`. Tests provide isolated settings and must not require a real OpenAI key unless explicitly marked as live integration tests.

## 10. Canonical local commands

These commands become authoritative after scaffolding:

```text
uv sync
uv run alembic upgrade head
uv run python -m agent_commerce.seed_demo
uv run uvicorn agent_commerce.main:app --reload
npm --prefix frontend ci
npm --prefix frontend run dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
npm --prefix frontend run lint
npm --prefix frontend run test
npm --prefix frontend run build
```

If scaffolding changes the exact commands, update this document, `README.md`, and `AGENTS.md` in the same change.

## 11. Test strategy

### Unit tests

- Money and total calculations.
- Constraint validation.
- State transitions.
- Approval coverage and invalidation.
- Payment simulator behavior.

### Contract tests

- Pydantic request/result schemas.
- MCP tool names and structured results.
- Stable error categories.
- Idempotency semantics.

### Integration tests

- REST against a temporary SQLite database.
- MCP calls against the mounted FastMCP application.
- Authorization, order, capture, cancellation, return, and refund workflows.

### End-to-end tests

- Canonical successful purchase.
- Changed checkout requiring reapproval.
- Delayed order followed by cancellation or return and refund.

Mock the OpenAI model for deterministic automated tests. Keep one explicitly invoked live-agent smoke test for rehearsal.

## 12. External integration order

1. Deterministic payment simulator.
2. Complete agent-to-MCP-to-order flow.
3. Reliable reapproval and refund scenarios.
4. Stripe test-mode card adapter using PaymentIntents with manual capture.
5. Optional deployment database change to PostgreSQL.

Do not block the judged flow on preview access to MPP, x402, AP2, or shared payment-token products. Reproduce their important architectural properties—scoped authority, exact binding, receipts, and pluggable rails—inside the stable contract first.

## 13. Decision owners

- Maciej owns the OpenAI Agents SDK orchestration implementation.
- Kuba owns FastAPI commerce services and the FastMCP merchant surface.
- Piotr owns policy, payment simulator, provider adapter, and financial audit behavior.
- Bartosz owns the React/TypeScript frontend, REST integration, and the end-to-end demo.

Framework or dependency changes affecting another owner require a recorded decision in `workstream-status.md`.

## 14. Primary references

- [OpenAI Agents SDK Python: MCP](https://openai.github.io/openai-agents-python/mcp/)
- [OpenAI Agents SDK Python: tracing](https://openai.github.io/openai-agents-python/tracing/)
- [Official MCP Python SDK](https://py.sdk.modelcontextprotocol.io/)
- [MCP SDK list](https://modelcontextprotocol.io/docs/sdk)
- [uv projects](https://docs.astral.sh/uv/concepts/projects/)
- [React documentation](https://react.dev/)
- [Vite documentation](https://vite.dev/)
