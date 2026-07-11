# Live workstream status

This is the team's lightweight coordination board. Update it when starting substantial work, changing a shared contract, becoming blocked, or handing off. Keep entries short and link to a branch, pull request, issue, or commit when available.

Last team sync: _not yet recorded_

## Current work

| Workstream | Human owner | Branch | Current outcome being built | Next integration point | Status/blocker |
|---|---|---|---|---|---|
| Agent and orchestration | Maciej | `codex/agent-orchestration` | Agent-generated four-parameter summary after semantic offer match | Bartosz verifies the live-agent wording in the UI | Ready to integrate |
| Commerce and MCP | Kuba | `codex/commerce-mcp` | FastAPI merchant domain plus FastMCP tools | Maciej/Piotr/Bartosz review the implemented contracts | Ready to integrate |
| Payments and trust | Piotr | `codex/payments-trust` | Stripe Elements card entry feeding a safe PaymentMethod ID into exact-checkout authorization | Bartosz verifies card entry and the canonical purchase in the browser | In progress |
| Experience and integration | Bartosz | `codex/experience` | Auto-growing chat composer and persistent multi-conversation sidebar | Team reviews the updated browser interaction | Ready to integrate |

Allowed status values: `Not started`, `In progress`, `Ready to integrate`, `Integrated`, or `Blocked: <reason>`.

## Shared interface changes

Record proposed or merged changes that affect another workstream.

| Date/time | Proposed by | Contract or operation | Change | Affected owners | Decision/status |
|---|---|---|---|---|---|
| 2026-07-11 | Kuba | Commerce REST/MCP contract | Implemented structured offers, versioned checkout, completion authority inputs, order/cancel/return, events, and stable errors | Maciej, Piotr, Bartosz | Ready for review on `codex/commerce-mcp` |
| 2026-07-11 | Piotr workstream | Trust/payment contract | Implemented mandates, proposal hashes, approvals, scoped credentials, authorize/capture/void/refund/recovery, and audit | Maciej, Kuba, Bartosz | Ready for review on `codex/payments-trust` |
| 2026-07-11 | Maciej workstream | Agent transaction contract | Implemented structured intent, read-only MCP planning, state machine, approval/execution, recovery, events, cancellation, and returns | Kuba, Piotr, Bartosz | Ready for review on `codex/agent-orchestration` |
| 2026-07-11 | Bartosz workstream | Frontend runtime and interaction model | Replace Streamlit's phased screens with a React/TypeScript single-chat UI; keep the existing REST transaction contract unchanged | All contributors (local setup), Maciej (API consumer) | Implemented and verified; ready for review |
| 2026-07-11 | Piotr workstream | Refund status contract | Add compatible `PENDING` and `FAILED` states so asynchronous Stripe refunds are not reported as completed; restore mandate spend only on `COMPLETED` | Maciej, Bartosz, Piotr | Implemented with contract and lifecycle tests; ready for review |
| 2026-07-11 | Piotr/Bartosz workstreams | Interactive payment handoff | Allow exact-checkout approval to carry a validated Stripe Elements `pm_...` ID for one authorization attempt; never persist it or accept raw card fields | Maciej, Piotr, Bartosz | Implemented; browser verification pending publishable test key |
| 2026-07-11 | Maciej workstream | Agent selection projection | Add four agent-generated `{label, value}` display parameters after a successful semantic match; UI renders the list without interpreting attribute names | Bartosz | Implemented and covered by backend contract/orchestration and frontend rendering tests |

## Canonical scenario health

The integration owner updates the first failing step. Do not mark later steps healthy if an earlier required step cannot run.

| Step | Status | Evidence or first failure |
|---|---|---|
| Submit canonical request | Passing | Agent REST endpoint and orchestration tests |
| Extract structured constraints | Passing | Structured OpenAI schema plus deterministic CI fallback |
| Search structured offers | Passing | Unit, MCP contract, and REST integration tests |
| Reject invalid offers and select one | Passing | Read-only planner enforces budget, compatibility, delivery, returns, and stock |
| Create authoritative checkout | Passing | Inventory reservation, version, expiry, totals, and idempotency tests |
| Present checkout proposal | Passing | Exact immutable proposal with hash, terms, and policy context |
| Approve exact checkout version | Passing | Explicit and mandate approval; automatic invalidation on checkout change |
| Authorize scoped payment | Passing | Single-use credential and exact merchant/checkout/amount/currency binding |
| Complete checkout idempotently | Passing | Exact approval/payment binding and duplicate completion tests |
| Confirm order and capture payment | Passing | Integrated API test covers merchant completion followed by capture |
| Display receipt and timeline | Passing | React chat renders authoritative order/payment state and expandable transaction activity |
| React to post-purchase event | Passing | Fulfillment transition and persisted merchant event tests |
| Cancel/return and track refund | Failing | Commerce emits `refund.pending`; Piotr's refund processing is not integrated yet |

Use status values `Not run`, `Failing`, or `Passing`.

## Active decisions and blockers

Only list decisions that prevent progress or affect multiple owners. Move durable outcomes into the architecture or shared-contract document.

| Item | Owner | Needed by | Options/context | Resolution |
|---|---|---|---|---|
| Assign names to the four workstreams | Team | Before implementation begins | Maciej: agent; Kuba: commerce/MCP; Piotr: payments/trust; Bartosz: experience/integration | Resolved |
| Choose implementation stack | Team | Before walking skeleton | Python 3.12, uv, FastAPI, OpenAI Agents SDK, FastMCP, SQLAlchemy/SQLite, React/TypeScript/Vite | Resolved; frontend amendment recorded in `docs/technology-stack.md` |
| Select primary payment demo rail | Piotr | Before credible-transaction milestone | Deterministic Python simulator first; Stripe test mode optional behind adapter | Simulator is baseline; external rail remains optional |
| Replace Streamlit with React | Bartosz | Before UI integration | The continuous chat needs richer in-place approval, status, and responsive interaction than the current phased Streamlit reruns provide | React/TypeScript with Vite accepted for the frontend; backend/domain boundaries remain unchanged |

## Handoffs

Use one row per meaningful handoff. Detailed notes can live in the linked change.

| Date/time | From | To | Outcome | Changed interfaces | Verification/link |
|---|---|---|---|---|---|
| 2026-07-11 | Kuba | Maciej, Piotr, Bartosz | Commerce service, REST API, and FastMCP surface ready for integration | Models and operations in `docs/shared-contracts.md`; implementation contracts in `backend/src` | `backend/README.md`; commerce test suite |
| 2026-07-11 | Piotr workstream | Maciej, Kuba, Bartosz | Trust, payment, audit, and recovery services ready for integration | Adds product category to checkout lines; trust/payment REST surfaces and automatic checkout invalidation | `backend/PAYMENTS_TRUST.md`; trust/payment tests |
| 2026-07-11 | Maciej workstream | Kuba, Piotr, Bartosz | Agent orchestration and transaction projection ready for integration | Adds merchant lookup by checkout; agent REST surface; OpenAI/MCP and deterministic runtime modes | `backend/AGENT_ORCHESTRATION.md`; orchestration and MCP integration tests |
| 2026-07-11 14:57 CEST | Bartosz workstream | Team | Responsive single-chat React experience from intent through approval, purchase, tracking, and resolution | Frontend runtime changed; REST/domain contracts unchanged | Frontend lint/test/build and 40 backend tests pass |
| 2026-07-11 | Bartosz workstream | Team | Auto-growing message composer and switchable persistent conversation history | Browser-only safe summary index; backend contracts unchanged | Frontend lint, 9 tests, and production build pass |
| 2026-07-11 | Bartosz workstream | Team | Non-blocking conversation navigation while agent/API work remains in flight | View-scoped response handling; backend contracts unchanged | Frontend lint, 10 tests, and production build pass |
| 2026-07-11 | Bartosz workstream | Team | Clarification replies and immediate optimistic conversation entries | Clarifications create a new authoritative transaction and replace the prior UI entry; backend contracts unchanged | Frontend lint, 12 tests, and production build pass |
| 2026-07-11 | Bartosz workstream | Team | Live spoken prompt input using OpenAI Realtime transcription over browser WebRTC | Adds a backend-only SDP exchange endpoint; commerce and transaction contracts unchanged | Contract/unit tests added; live-key browser smoke test required |
| 2026-07-11 | Bartosz workstream | Team | Configurable backend pacing exposes authorization, merchant confirmation, capture, and fulfillment as live approval-card states | Adds optional `DEMO_STEP_DELAY_MS`; transaction contracts unchanged | 20 focused backend tests, frontend lint, 18 tests, and production build pass |
| 2026-07-11 | Piotr workstream | Maciej, Bartosz | Stripe test-mode authorization, capture, void, decline, refund, safe retries, and provider selection | Compatible refund status extension adds `PENDING` and `FAILED`; simulator remains default | Ruff, format check, mypy, and 53 backend tests pass |
