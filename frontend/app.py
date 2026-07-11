"""Approval and observability surface for the canonical commerce journey."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from uuid import uuid4

import streamlit as st
from api_client import BackendAPIError, CommerceAPIClient
from demo_flow import (
    CANONICAL_REQUEST,
    canonical_constraints,
    demo_authority,
    evaluate_offer,
    format_money,
    proposal_binding,
    select_delivery,
    select_offer,
)

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
        --ink:#13231f;
        --muted:#52635e;
        --accent:#e85d3f;
        --mint:#cde9dd;
        --paper:#f7f5ef;
        --surface:#ffffff;
    }
    .stApp { background: var(--paper); color: var(--ink); }
    .stApp [data-testid="stMarkdownContainer"],
    .stApp [data-testid="stCaptionContainer"],
    .stApp label,
    .stApp p { color: var(--ink); }

    /* Keep form controls readable regardless of the viewer's system theme. */
    .stApp [data-testid="stTextArea"] textarea,
    .stApp [data-testid="stTextInput"] input {
        background: var(--surface) !important;
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
        caret-color: var(--accent);
        border-color: #b8c2be;
    }
    .stApp [data-testid="stTextArea"] textarea::placeholder,
    .stApp [data-testid="stTextInput"] input::placeholder {
        color: #6d7a76 !important;
        opacity: 1;
    }
    .stApp [data-testid="stTextArea"] textarea:focus,
    .stApp [data-testid="stTextInput"] input:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 1px var(--accent) !important;
    }

    /* Alerts use pale backgrounds, so force their copy and icons to dark ink. */
    .stApp [data-testid="stAlert"] { color: var(--ink) !important; }
    .stApp [data-testid="stAlert"] * { color: var(--ink) !important; }

    .stApp [data-testid="stExpander"] {
        background: var(--surface);
        color: var(--ink);
        border-color: #dedbd1;
    }
    .stApp [data-testid="stExpander"] * { color: var(--ink); }
    .stApp code { color: #173c33; background: #eef3f0; }

    [data-testid="stSidebar"] { background: #13231f; }
    .stApp [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    .stApp [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    .stApp [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
    .stApp [data-testid="stSidebar"] label {
        color: #f7f5ef !important;
    }
    .stApp [data-testid="stSidebar"] .stButton button {
        background: #f7f5ef;
        border-color: #f7f5ef;
        color: #13231f !important;
    }
    .stApp [data-testid="stSidebar"] .stButton button p {
        color: #13231f !important;
    }
    .block-container { max-width: 1180px; padding-top: 2rem; }
    h1, h2, h3 { letter-spacing: -0.035em; }
    .eyebrow { color: #e85d3f; font-weight: 800; letter-spacing: .12em; font-size:.72rem; }
    .hero { font-size: clamp(2.5rem, 6vw, 5.2rem); line-height:.94; margin:.3rem 0 1rem; }
    .subtle { color: #65736f; }
    .card { background:#fff; border:1px solid #dedbd1; border-radius:18px; padding:1.25rem; }
    .state { display:inline-block; border-radius:999px; background:#cde9dd; padding:.3rem .7rem;
             font-size:.75rem; font-weight:800; letter-spacing:.04em; }
    .demo {
        background:#fff0cc; border:1px solid #e8c66d;
        border-radius:10px; padding:.65rem .8rem;
    }
    [data-testid="stSidebar"] .demo,
    [data-testid="stSidebar"] .demo * { color:#342b16 !important; }
    .timeline { border-left:2px solid #c9d4cf; margin-left:.45rem; padding-left:1.2rem; }
    .timeline-item { margin:0 0 1.1rem; }
    .timeline-item b { display:block; }
    div[data-testid="stMetric"] {
        background:#fff; border:1px solid #dedbd1;
        padding:1rem; border-radius:14px;
    }
    div[data-testid="stMetric"] * { color:var(--ink) !important; }
    .stButton > button { color:var(--ink); background:#fff; border-color:#aab7b2; }
    .stButton > button p { color:inherit; }
    .stButton > button[kind="primary"] { background:#e85d3f; border-color:#e85d3f; color:#fff; }
    .stButton > button:disabled { color:#697671; background:#e6e6e1; }
    </style>
    """,
    unsafe_allow_html=True,
)

BACKEND_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")


def client() -> CommerceAPIClient:
    return CommerceAPIClient(BACKEND_URL)


def initialize_state() -> None:
    defaults: dict[str, Any] = {
        "phase": "INTENT",
        "intent": CANONICAL_REQUEST,
        "constraints": None,
        "offers": [],
        "selected_offer": None,
        "checkout": None,
        "order": None,
        "return_record": None,
        "transaction_id": None,
        "local_events": [],
        "approval_binding": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def reset_session() -> None:
    for key in list(st.session_state):
        del st.session_state[key]
    st.rerun()


def add_local_event(title: str, detail: str, status: str = "done") -> None:
    st.session_state.local_events.append(
        {
            "title": title,
            "detail": detail,
            "status": status,
            "occurred_at": datetime.now().isoformat(),
        }
    )


def run_action(action: Any) -> Any | None:
    try:
        return action()
    except BackendAPIError as exc:
        st.error(f"{exc.code}: {exc.message}")
    except ValueError as exc:
        st.error(str(exc))
    return None


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## ◒ ARC")
        st.caption("Agent Commerce Gateway")
        api = client()
        online = api.health()
        api.close()
        st.markdown("---")
        st.markdown(f"**Commerce API**  {'● Online' if online else '○ Offline'}")
        st.caption(BACKEND_URL)
        st.markdown(
            '<div class="demo"><b>Integration mode</b><br>Commerce is live. Agent, approval, '
            "and payment services are deterministic demo adapters.</div>",
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
        reached = {name for name, _ in steps[: [name for name, _ in steps].index(current) + 1]}
        for name, label in steps:
            st.markdown(f"{'●' if name in reached else '○'} &nbsp; {label}")
        st.markdown("---")
        if st.button("Reset UI session", use_container_width=True):
            reset_session()
        st.caption(
            "This clears UI state; the in-memory backend keeps created orders and reservations."
        )


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
        intent = st.text_area("Purchase request", value=st.session_state.intent, height=120)
        submitted = st.form_submit_button("Start transaction", type="primary")
    if not submitted:
        return

    def action() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        api = client()
        try:
            constraints = canonical_constraints()
            offers = api.search_offers({"category": "monitor", "currency": "PLN", "quantity": 1})
            selected = select_offer(offers, constraints)
            return offers, selected, constraints
        finally:
            api.close()

    result = run_action(action)
    if result:
        offers, selected, constraints = result
        st.session_state.intent = intent
        st.session_state.transaction_id = f"txn_{uuid4().hex}"
        st.session_state.constraints = constraints
        st.session_state.offers = offers
        st.session_state.selected_offer = selected
        add_local_event(
            "Intent captured", "Purchase objective received; no spending authority granted."
        )
        add_local_event(
            "Constraints extracted", "Deterministic demo parser produced six hard constraints."
        )
        st.session_state.phase = "OFFERS"
        st.rerun()


def render_constraints() -> None:
    constraints = st.session_state.constraints
    if not constraints:
        return
    st.markdown("### Interpreted request")
    cols = st.columns(4)
    cols[0].metric("Budget ceiling", format_money(constraints["max_unit_price_minor"], "PLN"))
    cols[1].metric("Compatibility", "Mac")
    cols[2].metric("Delivery by", constraints["latest_delivery_date"])
    cols[3].metric("Return window", f"≥ {constraints['minimum_return_window_days']} days")
    st.caption("Extracted by the deterministic demo adapter. This intent is not approval to spend.")


def render_offers() -> None:
    render_constraints()
    st.markdown("### Decision record")
    selected_id = st.session_state.selected_offer["offer_id"]
    for offer in st.session_state.offers:
        failures = evaluate_offer(offer, st.session_state.constraints)
        selected = offer["offer_id"] == selected_id
        with st.container(border=True):
            left, middle, right = st.columns([4, 2, 2])
            left.markdown(f"**{offer['product']['name']}**  ·  {offer['variant']}")
            left.caption(offer["product"]["description"])
            offer_price = format_money(
                offer["unit_price"]["amount_minor"], offer["unit_price"]["currency"]
            )
            middle.markdown(f"**{offer_price}**")
            middle.caption(f"{offer['return_policy']['window_days']}-day returns")
            if selected:
                right.success("Recommended")
            elif failures:
                right.error("Rejected")
                right.caption(" · ".join(failures))
            else:
                right.info("Eligible alternative")

    chosen = st.session_state.selected_offer
    st.info(
        f"Recommended: **{chosen['product']['name']}**. It satisfies every hard constraint and "
        "maximizes screen size among eligible offers."
    )
    if st.button("Create exact checkout", type="primary"):
        delivery = select_delivery(chosen, st.session_state.constraints["latest_delivery_date"])

        def action() -> dict[str, Any]:
            api = client()
            try:
                return api.create_checkout(
                    {
                        "transaction_id": st.session_state.transaction_id,
                        "selections": [
                            {
                                "offer_id": chosen["offer_id"],
                                "offer_version": chosen["version"],
                                "quantity": 1,
                            }
                        ],
                        "delivery_option_id": delivery["delivery_option_id"],
                        "idempotency_key": f"ui-create-{st.session_state.transaction_id}",
                    }
                )
            finally:
                api.close()

        checkout = run_action(action)
        if checkout:
            st.session_state.checkout = checkout
            st.session_state.approval_binding = proposal_binding(checkout)
            add_local_event(
                "Offer selected",
                f"Selected {chosen['product']['name']} after constraint checks.",
            )
            add_local_event(
                "Checkout created",
                f"Merchant reserved inventory in {checkout['checkout_id']} v{checkout['version']}.",
            )
            add_local_event(
                "Approval requested",
                "Waiting for consent bound to the exact checkout snapshot.",
                "pending",
            )
            st.session_state.phase = "CHECKOUT"
            st.rerun()


def render_checkout() -> None:
    checkout = st.session_state.checkout
    st.markdown("### Exact checkout proposal")
    st.markdown(
        f'<span class="state">AWAITING APPROVAL · v{checkout["version"]}</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")
    left, right = st.columns([3, 2])
    with left, st.container(border=True):
        for line in checkout["lines"]:
            st.markdown(f"#### {line['product_name']}")
            st.caption(
                f"{line['variant']} · Qty {line['quantity']} · Offer v{line['offer_version']}"
            )
        st.markdown(f"**Delivery:** {checkout['delivery_option']['label']}")
        st.caption(f"Promised for {checkout['delivery_option']['estimated_delivery_date']}")
        st.markdown(f"**Returns:** {checkout['return_policy']['description']}")
        st.caption(f"Reserved until {checkout['reserved_until']}")
    with right:
        price = checkout["price"]
        with st.container(border=True):
            st.markdown("#### Merchant total")
            st.write("Subtotal", format_money(price["subtotal_minor"], price["currency"]))
            st.write("Shipping", format_money(price["shipping_minor"], price["currency"]))
            tax = (
                "Included"
                if price["tax_included"]
                else format_money(price["tax_minor"], price["currency"])
            )
            st.write("Tax", tax)
            st.divider()
            st.markdown(f"## {format_money(price['total_minor'], price['currency'])}")

    with st.expander("Approval binding and identifiers"):
        st.code(
            f"checkout: {checkout['checkout_id']}\nversion: {checkout['version']}\n"
            f"merchant: {checkout['merchant_id']}\n"
            f"proposal sha256: {st.session_state.approval_binding}"
        )

    consent = st.checkbox(
        f"I approve checkout {checkout['checkout_id']} v{checkout['version']} for exactly "
        f"{format_money(checkout['price']['total_minor'], checkout['price']['currency'])}."
    )
    st.caption("Approval expires with this checkout. Any material change requires new approval.")
    left_button, _ = st.columns([1, 3])
    if left_button.button("Approve & purchase", type="primary", disabled=not consent):
        approval, payment = demo_authority(checkout)

        def action() -> dict[str, Any]:
            api = client()
            try:
                return api.complete_checkout(
                    checkout["checkout_id"],
                    {
                        "checkout_id": checkout["checkout_id"],
                        "expected_version": checkout["version"],
                        "approval": approval,
                        "payment_authorization": payment,
                        "idempotency_key": f"ui-complete-{st.session_state.transaction_id}",
                    },
                )
            finally:
                api.close()

        order = run_action(action)
        if order:
            st.session_state.order = order
            st.session_state.local_events[-1] = {
                "title": "Approval granted",
                "detail": (
                    f"Demo approval bound to {checkout['checkout_id']} v{checkout['version']}."
                ),
                "status": "done",
                "occurred_at": datetime.now().isoformat(),
            }
            add_local_event(
                "Payment authorized", "Demo adapter authorized the exact merchant amount."
            )
            add_local_event(
                "Order confirmed",
                f"Merchant returned authoritative order {order['order_id']}.",
            )
            add_local_event(
                "Payment captured", "Simulated receipt recorded after order confirmation."
            )
            st.session_state.phase = "ORDER"
            st.rerun()


def render_order() -> None:
    order = st.session_state.order
    st.success(f"Order confirmed · {order['order_id']}")
    left, middle, right = st.columns(3)
    left.metric("Order state", order["state"].title())
    middle.metric(
        "Paid (simulated)",
        format_money(order["price"]["total_minor"], order["price"]["currency"]),
    )
    right.metric("Delivery", order["delivery_option"]["estimated_delivery_date"])
    st.caption(
        "Order confirmation and fulfillment are merchant-authoritative. Capture is displayed "
        "from the temporary demo payment adapter."
    )

    st.markdown("### Manage this order")
    state = order["state"]
    controls = st.columns(3)
    next_state = {
        "CONFIRMED": "PROCESSING",
        "PROCESSING": "SHIPPED",
        "SHIPPED": "DELIVERED",
    }.get(state)
    if next_state and controls[0].button(f"Advance to {next_state.title()}"):

        def advance() -> dict[str, Any]:
            api = client()
            try:
                return api.set_order_state(
                    order["order_id"],
                    next_state,
                    f"ui-state-{order['order_id']}-{next_state}",
                )
            finally:
                api.close()

        updated = run_action(advance)
        if updated:
            st.session_state.order = updated
            add_local_event("Fulfillment updated", f"Merchant moved the order to {next_state}.")
            st.rerun()

    if order["cancellable"] and controls[1].button("Cancel order"):

        def cancel() -> dict[str, Any]:
            api = client()
            try:
                return api.cancel_order(order["order_id"], f"ui-cancel-{order['order_id']}")
            finally:
                api.close()

        updated = run_action(cancel)
        if updated:
            st.session_state.order = updated
            add_local_event("Order cancelled", "Merchant accepted cancellation; refund is pending.")
            st.session_state.phase = "RESOLVE"
            st.rerun()

    if state == "DELIVERED":
        reason = st.text_input("Return reason", value="Changed my mind")
        if controls[2].button("Create return"):
            items = {line["product_id"]: line["quantity"] for line in order["lines"]}

            def create_return() -> dict[str, Any]:
                api = client()
                try:
                    return api.create_return(
                        order["order_id"],
                        items,
                        reason,
                        f"ui-return-{order['order_id']}",
                    )
                finally:
                    api.close()

            record = run_action(create_return)
            if record:
                st.session_state.return_record = record
                add_local_event(
                    "Return authorized",
                    f"Return {record['return_id']} created; refund is pending.",
                )
                st.session_state.phase = "RESOLVE"
                st.rerun()


def render_resolution() -> None:
    order = st.session_state.order
    st.markdown("### Resolution in progress")
    if order["state"] == "CANCELLED":
        st.warning("Order cancelled · refund pending")
        st.metric(
            "Expected refund",
            format_money(order["price"]["total_minor"], order["price"]["currency"]),
        )
    if st.session_state.return_record:
        record = st.session_state.return_record
        st.info(f"Return {record['state'].lower()} · {record['return_id']}")
        st.metric(
            "Expected refund",
            format_money(
                record["refund_amount"]["amount_minor"], record["refund_amount"]["currency"]
            ),
        )
    st.caption(
        "The commerce backend emitted refund.pending. Payment-side refund processing is not "
        "integrated yet."
    )


def render_timeline() -> None:
    if not st.session_state.transaction_id:
        return
    remote_events: list[dict[str, Any]] = []
    api = client()
    try:
        remote_events = api.list_events(st.session_state.transaction_id)
    except BackendAPIError:
        pass
    finally:
        api.close()
    with st.expander(
        "Transaction timeline", expanded=st.session_state.phase in {"ORDER", "RESOLVE"}
    ):
        st.caption(f"Correlation · {st.session_state.transaction_id}")
        st.markdown('<div class="timeline">', unsafe_allow_html=True)
        for event in st.session_state.local_events:
            st.markdown(
                f'<div class="timeline-item"><b>{event["title"]}</b>'
                f'<span class="subtle">{event["detail"]}</span></div>',
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)
        if remote_events:
            st.caption(f"{len(remote_events)} merchant event(s) persisted for this transaction.")
            with st.popover("Inspect merchant events"):
                st.json(remote_events)


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
