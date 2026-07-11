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
Set `BACKEND_REQUEST_TIMEOUT_SECONDS` to control how long Streamlit waits for agent operations;
the default is 300 seconds because high-reasoning model runs can make several MCP calls.

## Integration boundary

- Streamlit calls the backend REST API only; it does not import backend services or repositories.
- Intent extraction, offer selection, checkout creation, proposal binding, approval validation,
  scoped payment authorization, order creation, capture, cancellation, return, and refund are
  executed by the backend orchestration endpoint.
- The frontend stores only safe API projections and never creates approval evidence, payment
  credentials, or authoritative transaction state.
- `Reset UI session` clears Streamlit state only; it does not reset the backend's in-memory
  merchant data.
