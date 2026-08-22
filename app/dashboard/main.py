"""Streamlit HITL dashboard (Fase 4.1).

    streamlit run app/dashboard/main.py
"""

from __future__ import annotations

import os
import time

import httpx
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
OPERATOR_ID = os.getenv("OPERATOR_ID", "op_joao")

STATUS_COLOURS = {
    "awaiting_human": "🟡",
    "escalated": "🔴",
    "delegated": "🔵",
    "quarantined": "⚫",
    "resolved": "🟢",
    "open": "⚪",
    "discarded": "🔘",
}

FILTERS = {
    "Todos": {},
    "Meus": {"assigned_operator_id": OPERATOR_ID},
    "HITL": {"status": "awaiting_human"},
    "Delegados": {"status": "delegated"},
    "Quarentena": {"status": "quarantined"},
}

FILTER_STAT_KEYS = {
    "Todos": None,
    "Meus": None,
    "HITL": "awaiting_human",
    "Delegados": "delegated",
    "Quarentena": "quarantined",
}


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE_URL, timeout=15.0)


def _get(path: str, params: dict | None = None) -> httpx.Response:
    with _client() as client:
        return client.get(path, params=params)


def _post(path: str, json: dict) -> httpx.Response:
    with _client() as client:
        return client.post(path, json=json)


def _badge(status: str) -> str:
    return f"{STATUS_COLOURS.get(status, '⚪')} {status}"


def _confidence_label(value: float | None) -> str:
    if value is None:
        return "—"
    colour = "🟢" if value >= 0.7 else "🟡"
    return f"{colour} {value:.2f}"


def _init_state() -> None:
    st.session_state.setdefault("filter", "Todos")
    st.session_state.setdefault("selected_ticket_id", None)
    st.session_state.setdefault("auto_refresh_interval", 0)


def _filter_count(stats: dict[str, int], label: str, meus_count: int) -> int:
    if label == "Todos":
        return sum(stats.values())
    if label == "Meus":
        return meus_count
    key = FILTER_STAT_KEYS[label]
    return int(stats.get(key, 0)) if key else 0


st.set_page_config(page_title="P2P HITL Dashboard", layout="wide")
_init_state()

with st.sidebar:
    st.title("P2P Operator")
    st.caption(f"Operator: `{OPERATOR_ID}`")
    try:
        stats_resp = _get("/stats")
        stats_resp.raise_for_status()
        stats = stats_resp.json()
    except httpx.HTTPError as exc:
        st.error(f"Cannot load stats from API: {exc}")
        stats = {key: 0 for key in STATUS_COLOURS}

    meus_count = 0
    try:
        meus_resp = _get("/tickets", params={"assigned_operator_id": OPERATOR_ID})
        if meus_resp.is_success:
            meus_count = len(meus_resp.json())
    except httpx.HTTPError:
        meus_count = 0

    for label in FILTERS:
        count = _filter_count(stats, label, meus_count)
        if st.button(f"{label} ({count})", key=f"filter_{label}", use_container_width=True):
            st.session_state["filter"] = label
            st.session_state["selected_ticket_id"] = None

    st.markdown(f"**Filter:** {st.session_state['filter']}")
    st.session_state["auto_refresh_interval"] = st.slider(
        "Auto-refresh (seconds)",
        min_value=0,
        max_value=60,
        value=int(st.session_state["auto_refresh_interval"]),
        help="0 = off. Polling via sleep + rerun, not websockets.",
    )
    if st.button("Refresh", use_container_width=True):
        st.rerun()

st.header("Tickets")
params = FILTERS[st.session_state["filter"]]
try:
    list_resp = _get("/tickets", params=params)
    list_resp.raise_for_status()
    tickets = list_resp.json()
except httpx.HTTPError as exc:
    st.error(f"Cannot load tickets: {exc}")
    tickets = []

if tickets:
    rows = []
    for item in tickets:
        rows.append(
            {
                "id": item["id"],
                "timestamp": item.get("received_at"),
                "sender email": item.get("sender_email"),
                "intent": item.get("intent") or "—",
                "status": _badge(item.get("status") or ""),
                "confidence": _confidence_label(item.get("confidence")),
                "assigned_to": item.get("assigned_operator_id") or "—",
            }
        )
    frame_rows = rows
    selection = st.dataframe(
        frame_rows,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="ticket_table",
    )
    selected_rows = selection.selection.rows if selection and selection.selection else []
    if selected_rows:
        st.session_state["selected_ticket_id"] = frame_rows[selected_rows[0]]["id"]
else:
    st.info("No tickets for this filter.")

selected_id = st.session_state.get("selected_ticket_id")
if selected_id:
    try:
        detail_resp = _get(f"/tickets/{selected_id}")
        detail_resp.raise_for_status()
        detail = detail_resp.json()
    except httpx.HTTPError as exc:
        st.error(f"Cannot load ticket detail: {exc}")
        detail = None

    if detail:
        ticket = detail.get("ticket") or {}
        sender = detail.get("sender") or {}
        draft = detail.get("draft") or {}
        invoice = detail.get("invoice") or {}

        st.subheader("Ticket detail")
        left, right = st.columns(2)
        with left:
            st.markdown(f"**Subject:** {ticket.get('subject') or '—'}")
            st.text_area(
                "Email body",
                value=ticket.get("body") or "",
                height=240,
                disabled=True,
            )
            st.markdown(
                f"**Sender:** {sender.get('name') or '—'} / "
                f"{sender.get('company') or '—'} / {ticket.get('sender_email') or '—'}"
            )
            intent = ticket.get("intent")
            st.markdown(f"**Intent:** `{intent}`" if intent else "**Intent:** —")
            st.markdown(f"**message_id:** `{ticket.get('message_id') or '—'}`")

        with right:
            if invoice:
                st.markdown(
                    f"**Invoice:** `{invoice.get('invoice_ref')}` · "
                    f"{invoice.get('amount')} {invoice.get('currency')}"
                )
                st.markdown(
                    f"stage `{invoice.get('stage')}` · status `{invoice.get('status')}` · "
                    f"due {invoice.get('due_date') or '—'}"
                )
            else:
                st.markdown("**Invoice:** no match")
            st.markdown(f"**Confidence:** {_confidence_label(ticket.get('confidence'))}")
            st.text_area(
                "Operator notes",
                value=draft.get("operator_notes") or "",
                height=80,
                disabled=True,
            )
            generated = draft.get("generated_text") or ""
            edited_text = st.text_area(
                "Draft text",
                value=generated,
                height=200,
                key=f"draft_text_{selected_id}",
            )
            st.markdown(f"**to_email:** `{draft.get('to_email') or '—'}`")
            st.markdown(
                f"attach invoice PDF: `{draft.get('attach_invoice_pdf')}` · "
                f"attach payment proof: `{draft.get('attach_payment_proof')}`"
            )

        approve_col, edit_col, escalate_col = st.columns(3)
        with approve_col:
            if st.button("Approve"):
                resp = _post(
                    f"/tickets/{selected_id}/approve",
                    json={"operator_id": OPERATOR_ID},
                )
                if resp.is_success:
                    st.success("Approved")
                    st.session_state["selected_ticket_id"] = None
                    st.rerun()
                else:
                    st.error(resp.text)
        with edit_col:
            if st.button("Edit + Approve"):
                if edited_text.strip() == generated.strip():
                    st.warning("Edit the draft before Edit + Approve.")
                else:
                    resp = _post(
                        f"/tickets/{selected_id}/approve",
                        json={"operator_id": OPERATOR_ID, "final_text": edited_text},
                    )
                    if resp.is_success:
                        st.success("Approved")
                        st.session_state["selected_ticket_id"] = None
                        st.rerun()
                    else:
                        st.error(resp.text)
        with escalate_col:
            if st.button("Escalate"):
                resp = _post(
                    f"/tickets/{selected_id}/escalate",
                    json={"operator_id": OPERATOR_ID},
                )
                if resp.is_success:
                    st.warning("Escalated to manual")
                    st.session_state["selected_ticket_id"] = None
                    st.rerun()
                else:
                    st.error(resp.text)

interval = int(st.session_state["auto_refresh_interval"])
if interval > 0:
    time.sleep(interval)
    st.rerun()
