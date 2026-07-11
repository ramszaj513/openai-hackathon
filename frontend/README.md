# Experience and integration frontend

This Streamlit app tells the canonical transaction story from intent through post-purchase
resolution. It communicates with the backend exclusively over REST.

## Run locally

Start the backend and frontend from separate terminals:

```text
uv run uvicorn agent_commerce.main:app --reload --app-dir backend/src
uv run streamlit run frontend/app.py
```

Set `BACKEND_BASE_URL` if the backend is not available at `http://127.0.0.1:8000`.

## Current integration boundary

- Offers, checkout totals, inventory reservation, orders, fulfillment, returns, and merchant
  events come from the live commerce REST API.
- Intent extraction, offer choice, checkout proposal binding, approval, payment authorization,
  and capture receipt are deterministic demo adapters until the orchestration and trust APIs
  are integrated.
- Demo adapters use opaque references only. No credentials or payment secrets are stored in
  frontend state.
- `Reset UI session` clears Streamlit state only; it does not reset the backend's in-memory
  merchant data.
