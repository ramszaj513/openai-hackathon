# Live workstream status

This is the team's lightweight coordination board. Update it when starting substantial work, changing a shared contract, becoming blocked, or handing off. Keep entries short and link to a branch, pull request, issue, or commit when available.

Last team sync: _not yet recorded_

## Current work

| Workstream | Human owner | Branch | Current outcome being built | Next integration point | Status/blocker |
|---|---|---|---|---|---|
| Agent and orchestration | Maciej | `codex/agent-orchestration` | Canonical intent-to-order tool sequence with OpenAI Agents SDK | Search and checkout MCP contract | Not started |
| Commerce and MCP | Kuba | `codex/commerce-mcp` | FastAPI merchant domain plus FastMCP tools | Maciej/Piotr/Bartosz review the implemented contracts | Ready to integrate |
| Payments and trust | Piotr | `codex/payments-trust` | Checkout-bound approval and Python payment simulator | Approval and payment references for completion | Not started |
| Experience and integration | Bartosz | `codex/experience` | Streamlit intent, approval, and transaction timeline UI | Walking-skeleton end-to-end flow | Not started |

Allowed status values: `Not started`, `In progress`, `Ready to integrate`, `Integrated`, or `Blocked: <reason>`.

## Shared interface changes

Record proposed or merged changes that affect another workstream.

| Date/time | Proposed by | Contract or operation | Change | Affected owners | Decision/status |
|---|---|---|---|---|---|
| 2026-07-11 | Kuba | Commerce REST/MCP contract | Implemented structured offers, versioned checkout, completion authority inputs, order/cancel/return, events, and stable errors | Maciej, Piotr, Bartosz | Ready for review on `codex/commerce-mcp` |

## Canonical scenario health

The integration owner updates the first failing step. Do not mark later steps healthy if an earlier required step cannot run.

| Step | Status | Evidence or first failure |
|---|---|---|
| Submit canonical request | Not run | — |
| Extract structured constraints | Not run | — |
| Search structured offers | Passing | Unit, MCP contract, and REST integration tests |
| Reject invalid offers and select one | Not run | — |
| Create authoritative checkout | Passing | Inventory reservation, version, expiry, totals, and idempotency tests |
| Present checkout proposal | Not run | — |
| Approve exact checkout version | Not run | — |
| Authorize scoped payment | Not run | — |
| Complete checkout idempotently | Passing | Exact approval/payment binding and duplicate completion tests |
| Confirm order and capture payment | Not run | — |
| Display receipt and timeline | Not run | — |
| React to post-purchase event | Passing | Fulfillment transition and persisted merchant event tests |
| Cancel/return and track refund | Failing | Commerce emits `refund.pending`; Piotr's refund processing is not integrated yet |

Use status values `Not run`, `Failing`, or `Passing`.

## Active decisions and blockers

Only list decisions that prevent progress or affect multiple owners. Move durable outcomes into the architecture or shared-contract document.

| Item | Owner | Needed by | Options/context | Resolution |
|---|---|---|---|---|
| Assign names to the four workstreams | Team | Before implementation begins | Maciej: agent; Kuba: commerce/MCP; Piotr: payments/trust; Bartosz: experience/integration | Resolved |
| Choose implementation stack | Team | Before walking skeleton | Python 3.12, uv, FastAPI, OpenAI Agents SDK, FastMCP, SQLAlchemy/SQLite, Streamlit | Resolved; see `docs/technology-stack.md` |
| Select primary payment demo rail | Piotr | Before credible-transaction milestone | Deterministic Python simulator first; Stripe test mode optional behind adapter | Simulator is baseline; external rail remains optional |

## Handoffs

Use one row per meaningful handoff. Detailed notes can live in the linked change.

| Date/time | From | To | Outcome | Changed interfaces | Verification/link |
|---|---|---|---|---|---|
| 2026-07-11 | Kuba | Maciej, Piotr, Bartosz | Commerce service, REST API, and FastMCP surface ready for integration | Models and operations in `docs/shared-contracts.md`; implementation contracts in `backend/src` | `backend/README.md`; commerce test suite |
