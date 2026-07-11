"""Server-backed approval and observability UI for the commerce agent."""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import streamlit as st
from api_client import BackendAPIError, CommerceAPIClient
from presentation import CANONICAL_REQUEST, format_money

st.set_page_config(
    page_title="Arc · Agent Commerce",
    page_icon="◒",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --ink:#13231f; --muted:#52635e; --accent:#e85d3f;
        --paper:#f7f5ef; --surface:#ffffff;
    }
    .stApp { background:var(--paper); color:var(--ink); }
    .stApp [data-testid="stMarkdownContainer"],
    .stApp [data-testid="stCaptionContainer"],
    .stApp label, .stApp p { color:var(--ink); }
    .stApp [data-testid="stTextArea"] textarea,
    .stApp [data-testid="stTextInput"] input {
        background:var(--surface) !important;
        color:var(--ink) !important;
        -webkit-text-fill-color:var(--ink) !important;
        caret-color:var(--accent);
        border-color:#b8c2be;
    }
    .stApp [data-testid="stTextArea"] textarea::placeholder,
    .stApp [data-testid="stTextInput"] input::placeholder {
        color:#6d7a76 !important; opacity:1;
    }
    .stApp [data-testid="stAlert"],
    .stApp [data-testid="stAlert"] * { color:var(--ink) !important; }
    .stApp [data-testid="stExpander"] {
        background:var(--surface); color:var(--ink); border-color:#dedbd1;
    }
    .stApp [data-testid="stExpander"] * { color:var(--ink); }
    [data-testid="stSidebar"] { background:#13231f; }
    .stApp [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    .stApp [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    .stApp [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
    .stApp [data-testid="stSidebar"] label { color:#f7f5ef !important; }
    .stApp [data-testid="stSidebar"] .stButton button {
        background:#f7f5ef; border-color:#f7f5ef; color:#13231f !important;
    }
    .stApp [data-testid="stSidebar"] .stButton button p { color:#13231f !important; }
    .block-container { max-width:1180px; padding-top:2rem; }
    h1, h2, h3 { letter-spacing:-0.035em; }
    .eyebrow {
        color:var(--accent); font-weight:800; letter-spacing:.12em; font-size:.72rem;
    }
    .hero { font-size:clamp(2.5rem, 6vw, 5.2rem); line-height:.94; margin:.3rem 0 1rem; }
    .subtle { color:var(--muted); }
    .state {
        display:inline-block; border-radius:999px; background:#cde9dd;
        padding:.3rem .7rem; font-size:.75rem; font-weight:800;
    }
    .server-note {
        background:#fff0cc; border:1px solid #e8c66d;
        border-radius:10px; padding:.65rem .8rem;
    }
    [data-testid="stSidebar"] .server-note,
    [data-testid="stSidebar"] .server-note * { color:#342b16 !important; }
    .timeline { border-left:2px solid #c9d4cf; margin-left:.45rem; padding-left:1.2rem; }
    .timeline-item { margin:0 0 1.1rem; }
    .timeline-item b { display:block; }
    div[data-testid="stMetric"] {
        background:#fff; border:1px solid #dedbd1; padding:1rem; border-radius:14px;
    }
    div[data-testid="stMetric"] * { color:var(--ink) !important; }
    .stButton > button { color:var(--ink); background:#fff; border-color:#aab7b2; }
    .stButton > button p { color:inherit; }
    .stButton > button[kind="primary"] {
        background:var(--accent); border-color:var(--accent); color:#fff;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

BACKEND_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")
USER_ID = os.getenv("DEMO_USER_ID", "user-bartosz")
AGENT_ID = os.getenv("DEMO_AGENT_ID", "commerce-agent")


def client() -> CommerceAPIClient:
    return CommerceAPIClient(BACKEND_URL)


def initialize_state() -> None:
    defaults: dict[str, Any] = {
        "phase": "INTENT",
        "intent": CANONICAL_REQUEST,
        "purchase_request": CANONICAL_REQUEST,
        "transaction": None,
        "order": None,
        "payment": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def reset_session() -> None:
    for key in list(st.session_state):
        del st.session_state[key]
    st.rerun()


def run_action(action: Any) -> Any | None:
    try:
        return action()
    except BackendAPIError as exc:
        st.error(f"{exc.code}: {exc.message}")
    except ValueError as exc:
        st.error(str(exc))
    return None


def refresh_order_and_payment(transaction: dict[str, Any]) -> bool:
    if not transaction.get("order_id") or not transaction.get("payment_id"):
        st.error("The server transaction is missing its order or payment reference.")
        return False
    api = client()
    try:
        st.session_state.order = api.get_order(transaction["order_id"])
        st.session_state.payment = api.get_payment(transaction["payment_id"])
        return True
    except BackendAPIError as exc:
        st.error(f"{exc.code}: {exc.message}")
        return False
    finally:
        api.close()


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## ◒ ARC")
        st.caption("Agent Commerce Gateway")
        api = client()
        online = api.health()
        api.close()
        st.markdown("---")
        st.markdown(f"**Backend API**  {'● Online' if online else '○ Offline'}")
        st.caption(BACKEND_URL)
        st.markdown(
            '<div class="server-note"><b>Server mode</b><br>Agent, approval, payment, '
            "commerce, and order state all come from the backend API. Requests are made by "
            "the Streamlit Python process, not by browser JavaScript.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("---")
        steps = [
            ("INTENT", "01  Intent"),
            ("OFFERS", "02  Decide"),
            ("CHECKOUT", "03  Approve"),
            ("ORDER", "04  Purchase"),
            ("RESOLVE", "05  Resolve"),
        ]
        current = st.session_state.phase
        current_index = [name for name, _ in steps].index(current)
        reached = {name for name, _ in steps[: current_index + 1]}
        for name, label in steps:
            st.markdown(f"{'●' if name in reached else '○'} &nbsp; {label}")
        st.markdown("---")
        if st.button("Reset UI session", use_container_width=True):
            reset_session()
        st.caption("This clears browser state only. Server transactions remain authoritative.")


def render_header() -> None:
    st.markdown('<div class="eyebrow">AGENT-FIRST COMMERCE</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="hero">From intent<br>to resolution.</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="subtle">One continuous, auditable transaction story—with consent at the '
        "moment it matters.</p>",
        unsafe_allow_html=True,
    )


def render_intent() -> None:
    st.markdown("### What should the agent take care of?")
    with st.form("intent-form"):
        st.text_area("Purchase request", key="purchase_request", height=120)
        submitted = st.form_submit_button("Start transaction", type="primary")
    if not submitted:
        return
    intent = st.session_state.purchase_request.strip()
    if not intent:
        st.error("Enter a purchase request before starting the transaction.")
        return

    def action() -> dict[str, Any]:
        api = client()
        try:
            return api.start_transaction(
                {
                    "user_id": USER_ID,
                    "agent_id": AGENT_ID,
                    "raw_request": intent,
                    "payment_scenario": "APPROVE",
                    "idempotency_key": f"ui-start-{uuid4().hex}",
                }
            )
        finally:
            api.close()

    transaction = run_action(action)
    if not transaction:
        return
    st.session_state.intent = intent
    st.session_state.transaction = transaction
    if transaction["state"] == "FAILED":
        st.error(f"{transaction['last_error_code']}: {transaction['last_error_message']}")
        return
    if transaction["state"] == "CLARIFICATION_REQUIRED":
        st.warning(" ".join(transaction["intent"]["clarification_questions"]))
        with st.expander("Request received by the backend", expanded=True):
            st.code(transaction["raw_request"])
            st.caption(
                "Missing fields: "
                + ", ".join(transaction["intent"]["missing_required_fields"])
            )
        return
    st.session_state.phase = "OFFERS"
    st.rerun()


def render_constraints() -> None:
    intent = st.session_state.transaction["intent"]
    st.markdown("### Interpreted request")
    cols = st.columns(4)
    budget = intent.get("max_budget_minor")
    cols[0].metric(
        "Budget ceiling",
        format_money(budget, intent["currency"]) if budget is not None else "Not set",
    )
    required = intent.get("required_attributes", {})
    cols[1].metric("Compatibility", "Mac" if required.get("mac_compatible") else "Any")
    cols[2].metric("Delivery by", intent.get("latest_delivery_date") or "Not set")
    window = intent.get("minimum_return_window_days")
    cols[3].metric("Return window", f"≥ {window} days" if window is not None else "Any")
    st.caption("Extracted by the server-side commerce agent. This is not approval to spend.")


def render_offers() -> None:
    transaction = st.session_state.transaction
    selection = transaction["selection"]
    chosen = transaction["selected_offer"]
    render_constraints()
    st.markdown("### Decision record")
    with st.container(border=True):
        left, middle, right = st.columns([4, 2, 2])
        left.markdown(f"**{chosen['product']['name']}**  ·  {chosen['variant']}")
        left.caption(chosen["product"]["description"])
        price = chosen["unit_price"]
        middle.markdown(f"**{format_money(price['amount_minor'], price['currency'])}**")
        middle.caption(f"{chosen['return_policy']['window_days']}-day returns")
        right.success(f"Recommended · {selection['confidence']:.0%}")
    if selection["rejected_offers"]:
        with st.expander("Rejected offers"):
            for rejected in selection["rejected_offers"]:
                st.markdown(f"**{rejected['offer_id']}** — {'; '.join(rejected['reasons'])}")
    st.info(f"**Why this one:** {selection['selection_reason']}")
    if st.button("Review exact checkout", type="primary"):
        st.session_state.phase = "CHECKOUT"
        st.rerun()


def render_checkout() -> None:
    transaction = st.session_state.transaction
    checkout = transaction["checkout"]
    proposal = transaction["proposal"]
    st.markdown("### Exact checkout proposal")
    st.markdown(
        f'<span class="state">{proposal["status"].replace("_", " ")} · '
        f'v{proposal["checkout_version"]}</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")
    left, right = st.columns([3, 2])
    with left, st.container(border=True):
        for line in proposal["lines"]:
            st.markdown(f"#### {line['product_name']}")
            st.caption(
                f"{line['variant']} · Qty {line['quantity']} · Offer v{line['offer_version']}"
            )
        st.markdown(f"**Delivery:** {proposal['delivery_option']['label']}")
        st.caption(f"Promised for {proposal['delivery_option']['estimated_delivery_date']}")
        st.markdown(f"**Returns:** {proposal['return_policy']['description']}")
        st.caption(f"Checkout expires at {checkout['expires_at']}")
    with right, st.container(border=True):
        price = proposal["price"]
        st.markdown("#### Merchant total")
        st.write("Subtotal", format_money(price["subtotal_minor"], price["currency"]))
        st.write("Shipping", format_money(price["shipping_minor"], price["currency"]))
        st.write("Tax", "Included" if price["tax_included"] else price["tax_minor"])
        st.divider()
        st.markdown(f"## {format_money(price['total_minor'], price['currency'])}")
    with st.expander("Approval binding and identifiers"):
        st.code(
            f"transaction: {transaction['transaction_id']}\n"
            f"checkout: {proposal['checkout_id']}\n"
            f"version: {proposal['checkout_version']}\n"
            f"merchant: {proposal['merchant_id']}\n"
            f"proposal: {proposal['proposal_id']}\n"
            f"proposal sha256: {proposal['content_hash']}"
        )
    consent = st.checkbox(
        f"I approve checkout {proposal['checkout_id']} v{proposal['checkout_version']} for "
        f"exactly {format_money(price['total_minor'], price['currency'])}."
    )
    st.caption("The server binds consent to this hash. Material changes require new approval.")
    if st.button("Approve & purchase", type="primary", disabled=not consent):

        def action() -> dict[str, Any]:
            api = client()
            try:
                return api.approve_transaction(
                    transaction["transaction_id"],
                    {
                        "transaction_id": transaction["transaction_id"],
                        "user_id": transaction["user_id"],
                        "approved_content_hash": proposal["content_hash"],
                        "idempotency_key": f"ui-approve-{transaction['transaction_id']}",
                    },
                )
            finally:
                api.close()

        updated = run_action(action)
        if not updated:
            return
        st.session_state.transaction = updated
        if updated["state"] == "FAILED":
            st.error(f"{updated['last_error_code']}: {updated['last_error_message']}")
            return
        if refresh_order_and_payment(updated):
            st.session_state.phase = "ORDER"
            st.rerun()


def render_order() -> None:
    transaction = st.session_state.transaction
    order = st.session_state.order
    payment = st.session_state.payment
    st.success(f"Order confirmed · {order['order_id']}")
    left, middle, right = st.columns(3)
    left.metric("Order state", order["state"].title())
    middle.metric("Payment", payment["status"].title())
    right.metric("Delivery", order["delivery_option"]["estimated_delivery_date"])
    st.caption("Order, payment, and fulfillment state are loaded from the backend.")
    st.markdown("### Manage this order")
    controls = st.columns(3)
    next_state = {
        "CONFIRMED": "PROCESSING",
        "PROCESSING": "SHIPPED",
        "SHIPPED": "DELIVERED",
    }.get(order["state"])
    if next_state and controls[0].button(f"Advance to {next_state.title()}"):

        def advance() -> tuple[dict[str, Any], dict[str, Any]]:
            api = client()
            try:
                updated_order = api.set_order_state(
                    order["order_id"],
                    next_state,
                    f"ui-state-{order['order_id']}-{next_state}",
                )
                updated_transaction = api.resume_transaction(transaction["transaction_id"])
                return updated_order, updated_transaction
            finally:
                api.close()
        result = run_action(advance)
        if result:
            st.session_state.order, st.session_state.transaction = result
            st.rerun()
    if order["cancellable"] and controls[1].button("Cancel order"):

        def cancel() -> dict[str, Any]:
            api = client()
            try:
                return api.cancel_transaction(
                    transaction["transaction_id"],
                    {
                        "transaction_id": transaction["transaction_id"],
                        "reason": "User requested cancellation",
                        "idempotency_key": f"ui-cancel-{transaction['transaction_id']}",
                    },
                )
            finally:
                api.close()

        updated = run_action(cancel)
        if updated:
            st.session_state.transaction = updated
            refresh_order_and_payment(updated)
            st.session_state.phase = "RESOLVE"
            st.rerun()
    if order["state"] == "DELIVERED":
        reason = st.text_input("Return reason", value="Changed my mind")
        if controls[2].button("Create return"):
            items = {line["product_id"]: line["quantity"] for line in order["lines"]}

            def create_return() -> dict[str, Any]:
                api = client()
                try:
                    return api.return_transaction(
                        transaction["transaction_id"],
                        {
                            "transaction_id": transaction["transaction_id"],
                            "items": items,
                            "reason": reason,
                            "idempotency_key": f"ui-return-{transaction['transaction_id']}",
                        },
                    )
                finally:
                    api.close()

            updated = run_action(create_return)
            if updated:
                st.session_state.transaction = updated
                refresh_order_and_payment(updated)
                st.session_state.phase = "RESOLVE"
                st.rerun()


def render_resolution() -> None:
    transaction = st.session_state.transaction
    payment = st.session_state.payment
    st.markdown("### Resolution complete")
    st.success(transaction["state"].replace("_", " ").title())
    st.metric(
        "Refunded by server",
        format_money(payment["refunded_amount_minor"], payment["currency"]),
    )
    if transaction.get("return_id"):
        st.caption(f"Return · {transaction['return_id']}")
    st.caption(f"Payment {payment['payment_id']} · {payment['status']}")


def render_timeline() -> None:
    transaction = st.session_state.transaction
    if not transaction:
        return
    api = client()
    try:
        merchant_events = api.list_events(transaction["transaction_id"])
    except BackendAPIError:
        merchant_events = []
    finally:
        api.close()
    with st.expander(
        "Transaction timeline", expanded=st.session_state.phase in {"ORDER", "RESOLVE"}
    ):
        st.caption(f"Correlation · {transaction['transaction_id']}")
        st.markdown('<div class="timeline">', unsafe_allow_html=True)
        for event in transaction["transitions"]:
            state = event["to_state"].replace("_", " ").title()
            st.markdown(
                f'<div class="timeline-item"><b>{state}</b>'
                f'<span class="subtle">{event["reason"]}</span></div>',
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)
        if merchant_events:
            st.caption(f"{len(merchant_events)} persisted merchant event(s).")
            with st.popover("Inspect merchant events"):
                st.json(merchant_events)


initialize_state()
render_sidebar()
render_header()

phase = st.session_state.phase
if phase == "INTENT":
    render_intent()
elif phase == "OFFERS":
    render_offers()
elif phase == "CHECKOUT":
    render_checkout()
elif phase == "ORDER":
    render_order()
elif phase == "RESOLVE":
    render_resolution()

render_timeline()
