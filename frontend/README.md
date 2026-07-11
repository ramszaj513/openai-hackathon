# Arc single-chat frontend

The React/TypeScript application tells the complete commerce transaction story in one chat: intent, deterministic offer selection, exact checkout approval, confirmed order, fulfillment, cancellation or return, and refund.

## Run locally

Start the backend from the repository root:

```bash
uv run uvicorn agent_commerce.main:app --reload
```

Then start the frontend:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` and `/health` to `http://127.0.0.1:8000`. For a separately hosted backend, set `VITE_API_BASE_URL` at build time.

## Boundaries

- The browser uses REST only and never imports backend services or repositories.
- Totals, approval validity, payment authorization, order confirmation, refunds, and state transitions remain backend-authoritative.
- Explicit consent includes the checkout ID, version, exact total, currency, merchant-bound proposal hash, and expiry.
- The active transaction ID is kept in local storage only so the UI can reconstruct safe projections after a refresh.

## Verify

```bash
npm run lint
npm run test
npm run build
```
