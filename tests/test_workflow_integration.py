"""Test Gate 2 — full TicketWorkflow integration tests (Day 2).

These tests call TicketWorkflow(deps).run(...) directly (no Celery).
LLM calls are mocked via MockLLMAdapter. SAP data is from Day 0 fixtures.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.adapters.memory_audit import InMemoryAuditLog
from app.adapters.memory_draft import InMemoryDraftStore
from app.adapters.memory_ticket_store import InMemoryTicketStore
from app.adapters.mock_email import MockEmailAdapter
from app.adapters.mock_llm import MockLLMAdapter
from app.adapters.mock_sap import MockSAPAdapter
from app.adapters.mock_senders import MockSenderDirectory
from app.domain.deps import WorkflowDeps
from app.domain.enums import AuditAction, DraftTarget, TicketStatus
from app.domain.models import Ticket
from app.llm.exceptions import LLMUnavailableError
from app.workflow.ticket_workflow import TicketWorkflow
from settings import Settings

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "emails"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(**overrides) -> Settings:
    base = {
        "_env_file": None,
        "DATABASE_URL": "sqlite://",
        "NYLAS_SEND_ENABLED": False,
        "SPF_DKIM_ENABLED": False,
        "SECURITY_CHECK_ENABLED": False,
        "TRIAGE_DISCARD_MIN_CONFIDENCE": 0.8,
        "INTENT_MIN_CONFIDENCE": 0.5,
    }
    base.update(overrides)
    return Settings(**base)


def _deps(
    settings: Settings | None = None,
    llm_responses: list | None = None,
    ticket_store: InMemoryTicketStore | None = None,
    draft_store: InMemoryDraftStore | None = None,
    audit: InMemoryAuditLog | None = None,
) -> WorkflowDeps:
    return WorkflowDeps(
        settings=settings or _settings(),
        llm=MockLLMAdapter(llm_responses or []),
        email=MockEmailAdapter(),
        tickets=ticket_store or InMemoryTicketStore(),
        sap=MockSAPAdapter(),
        audit=audit or InMemoryAuditLog(),
        senders=MockSenderDirectory(),
        drafts=draft_store or InMemoryDraftStore(),
    )


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _event_from_fixture(fixture_name: str, *, thread_id: str, message_id: str) -> dict:
    fx = _load_fixture(fixture_name)
    inp = fx["input"]
    return {
        "thread_id": thread_id,
        "message_id": message_id,
        "from_email": inp.get("from", inp.get("from_email", "")),
        "subject": inp.get("subject", ""),
        "body": inp.get("body", ""),
        "attachments": [
            {"filename": a} if isinstance(a, str) else a
            for a in inp.get("attachments", [])
        ],
    }


# Standard LLM responses for AP tickets that proceed to DraftNode.
_TRIAGE_AP = {"is_ap": True, "confidence": 0.95}
_TRIAGE_NOT_AP = {"is_ap": False, "confidence": 0.92}
_DRAFT_TEXT = {"generated_text": "This is a generated draft reply."}

_INTENT_PAYMENT_STATUS_TEMPLATE = {
    "intent": "payment_status",
    "confidence": 0.9,
    "language": "en",
}


def _intent(ref: str | None = None, amount: str | None = None) -> dict:
    return {
        **_INTENT_PAYMENT_STATUS_TEMPLATE,
        "extracted_ref": ref,
        "extracted_amount": amount,
    }


# ---------------------------------------------------------------------------
# Fixture 001 — invoice NOT found  →  INVOICING target
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_001_invoice_not_found():
    deps = _deps(
        llm_responses=[
            _TRIAGE_AP,
            _intent("INV-2026-9999", "1000.00"),
            _DRAFT_TEXT,
        ]
    )
    event = _event_from_fixture("001_invoice_not_found.json", thread_id="t-001", message_id="m-001")
    ctx = await TicketWorkflow(deps).run_async(event)

    assert ctx.ticket is not None
    assert ctx.ticket.status == TicketStatus.AWAITING_HUMAN
    assert ctx.draft is not None
    assert ctx.draft.target == DraftTarget.INVOICING
    assert ctx.draft.to_email == deps.settings.INVOICING_EMAIL
    assert ctx.draft.attach_invoice_pdf is True


# ---------------------------------------------------------------------------
# Fixture 002 — IN_APPROVAL on-time  →  SENDER target
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_002_in_approval_on_time():
    deps = _deps(
        llm_responses=[
            _TRIAGE_AP,
            _intent("INV-2026-0008", "6150.00"),
            _DRAFT_TEXT,
        ]
    )
    event = _event_from_fixture("002_in_approval_on_time.json", thread_id="t-002", message_id="m-002")
    ctx = await TicketWorkflow(deps).run_async(event)

    assert ctx.ticket is not None
    assert ctx.ticket.status == TicketStatus.AWAITING_HUMAN
    assert ctx.draft is not None
    assert ctx.draft.target == DraftTarget.SENDER
    assert ctx.draft.to_email == "billing@acme-supplies.com"


# ---------------------------------------------------------------------------
# Fixture 003 — IN_APPROVAL overdue  →  APPROVAL_OWNERS target
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_003_in_approval_overdue():
    deps = _deps(
        llm_responses=[
            _TRIAGE_AP,
            _intent("INV-2026-0010", "6765.00"),
            _DRAFT_TEXT,
        ]
    )
    event = _event_from_fixture("003_in_approval_overdue.json", thread_id="t-003", message_id="m-003")
    ctx = await TicketWorkflow(deps).run_async(event)

    assert ctx.ticket is not None
    assert ctx.ticket.status == TicketStatus.AWAITING_HUMAN
    assert ctx.draft is not None
    assert ctx.draft.target == DraftTarget.APPROVAL_OWNERS


# ---------------------------------------------------------------------------
# Fixture 007 — PAID with clearing  →  SENDER + attach_payment_proof
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_007_paid_with_clearing():
    deps = _deps(
        llm_responses=[
            _TRIAGE_AP,
            _intent("INV-2026-0005", "14760.00"),
            _DRAFT_TEXT,
        ]
    )
    event = _event_from_fixture("007_paid_with_clearing.json", thread_id="t-007", message_id="m-007")
    ctx = await TicketWorkflow(deps).run_async(event)

    assert ctx.ticket is not None
    assert ctx.ticket.status == TicketStatus.AWAITING_HUMAN
    assert ctx.draft is not None
    assert ctx.draft.target == DraftTarget.SENDER
    assert ctx.draft.attach_payment_proof is True


# ---------------------------------------------------------------------------
# Fixture 011 — suspicious sender  →  QUARANTINED (stop at SecurityNode)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_011_suspicious_sender_quarantined():
    settings = _settings(SECURITY_CHECK_ENABLED=True)
    deps = _deps(settings=settings, llm_responses=[])
    event = _event_from_fixture(
        "011_suspicious_sender.json", thread_id="t-011", message_id="m-011"
    )
    ctx = await TicketWorkflow(deps).run_async(event)

    assert ctx.ticket is not None
    assert ctx.ticket.status == TicketStatus.QUARANTINED
    # Triage node must NOT have run (no LLM calls consumed)
    assert isinstance(deps.llm, MockLLMAdapter)
    assert len(deps.llm.calls) == 0


# ---------------------------------------------------------------------------
# Fixture 012 — not AP email  →  DISCARDED (stop at TriageNode)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_012_not_ap_email_discarded():
    deps = _deps(llm_responses=[_TRIAGE_NOT_AP])
    event = _event_from_fixture("012_not_ap_email.json", thread_id="t-012", message_id="m-012")
    ctx = await TicketWorkflow(deps).run_async(event)

    assert ctx.ticket is not None
    assert ctx.ticket.status == TicketStatus.DISCARDED


# ---------------------------------------------------------------------------
# Fixture 013 — delegated sender  →  DELEGATED (stop at RoutingNode)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_013_delegated_sender():
    deps = _deps(
        llm_responses=[
            _TRIAGE_AP,
            _intent("INV-2026-0002", "4920.00"),
        ]
    )
    event = _event_from_fixture("013_delegated_sender.json", thread_id="t-013", message_id="m-013")
    ctx = await TicketWorkflow(deps).run_async(event)

    assert ctx.ticket is not None
    assert ctx.ticket.status == TicketStatus.DELEGATED


# ---------------------------------------------------------------------------
# Fixture 014 — thread continuation  →  Triage/Intent/Sender/Routing skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_014_thread_continuation_skips_triage_intent():
    ticket_store = InMemoryTicketStore()
    existing = Ticket(
        id=uuid4(),
        thread_id="t-014",
        message_id="m-014-old",
        sender_email="billing@acme-supplies.com",
        subject="Payment status for INV-2026-0001",
        body="First message",
        received_at=datetime(2026, 8, 10, tzinfo=UTC),
        status=TicketStatus.AWAITING_HUMAN,
    )
    ticket_store.save_ticket(existing)

    deps = _deps(
        ticket_store=ticket_store,
        llm_responses=[_DRAFT_TEXT],  # only DraftNode LLM call expected
    )
    event = _event_from_fixture(
        "014_thread_continuation.json", thread_id="t-014", message_id="m-014-new"
    )
    ctx = await TicketWorkflow(deps).run_async(event)

    assert ctx.is_thread_continuation is True
    assert ctx.ticket is not None
    assert ctx.ticket.status == TicketStatus.AWAITING_HUMAN
    # Only 1 LLM call (DraftNode); Triage and Intent were skipped
    assert isinstance(deps.llm, MockLLMAdapter)
    assert len(deps.llm.calls) == 1


# ---------------------------------------------------------------------------
# Audit trail — for a full run, one entry per node executed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_trail_full_run():
    audit = InMemoryAuditLog()
    deps = _deps(
        audit=audit,
        llm_responses=[
            _TRIAGE_AP,
            _intent("INV-2026-9999", "500.00"),
            _DRAFT_TEXT,
        ],
    )
    event = _event_from_fixture("001_invoice_not_found.json", thread_id="t-a01", message_id="m-a01")
    ctx = await TicketWorkflow(deps).run_async(event)

    ticket_id = ctx.ticket.id
    entries = audit.get_by_ticket_id(ticket_id)

    # One entry per node; nodes run: Ingestion, Security, Thread, Triage, Intent,
    # Sender, Routing, Resolution, Draft, Hitl → 10 entries
    assert len(entries) == 10

    # Node names must be unique (one entry per class)
    node_names = [e.node for e in entries]
    assert len(node_names) == len(set(node_names))

    # All created_at values monotonically increase (or equal within same second)
    timestamps = [e.created_at for e in entries]
    assert timestamps == sorted(timestamps)

    # Last action must be HITL
    assert entries[-1].action == AuditAction.HITL


@pytest.mark.asyncio
async def test_audit_trail_stopped_at_security():
    audit = InMemoryAuditLog()
    settings = _settings(SECURITY_CHECK_ENABLED=True)
    deps = _deps(settings=settings, audit=audit)
    event = _event_from_fixture(
        "011_suspicious_sender.json", thread_id="t-a11", message_id="m-a11"
    )
    ctx = await TicketWorkflow(deps).run_async(event)
    entries = audit.get_by_ticket_id(ctx.ticket.id)

    # Ingestion + Security only
    assert len(entries) == 2
    assert entries[-1].action == AuditAction.QUARANTINE


# ---------------------------------------------------------------------------
# LLM unavailable  →  ESCALATED + audit entry with action=ESCALATE
# ---------------------------------------------------------------------------


class _AlwaysFailLLM(MockLLMAdapter):
    async def generate(self, *, system_prompt, user_prompt, output_schema):
        raise LLMUnavailableError("LLM down for test")


@pytest.mark.asyncio
async def test_llm_unavailable_escalates_ticket():
    audit = InMemoryAuditLog()
    deps = _deps(audit=audit)
    deps.llm = _AlwaysFailLLM()

    event = _event_from_fixture("001_invoice_not_found.json", thread_id="t-esc", message_id="m-esc")
    ctx = await TicketWorkflow(deps).run_async(event)

    assert ctx.ticket is not None
    assert ctx.ticket.status == TicketStatus.ESCALATED

    escalate_entries = [
        e for e in audit.entries if e.action == AuditAction.ESCALATE
    ]
    assert len(escalate_entries) >= 1


# ---------------------------------------------------------------------------
# Draft metadata is non-empty where applicable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_metadata_non_empty():
    audit = InMemoryAuditLog()
    deps = _deps(
        audit=audit,
        llm_responses=[
            _TRIAGE_AP,
            _intent("INV-2026-9999", "1000.00"),
            _DRAFT_TEXT,
        ],
    )
    event = _event_from_fixture("001_invoice_not_found.json", thread_id="t-dm", message_id="m-dm")
    ctx = await TicketWorkflow(deps).run_async(event)

    ticket_id = ctx.ticket.id
    draft_entry = next(e for e in audit.get_by_ticket_id(ticket_id) if e.action == AuditAction.DRAFT)
    assert draft_entry.metadata != {}
    assert "target" in draft_entry.metadata


# ---------------------------------------------------------------------------
# DraftNode target unit tests (no workflow — just node logic)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_node_not_found_target():
    from app.domain.context import ProcessingContext
    from app.domain.enums import InvoiceMatchResult
    from app.workflow.nodes.draft import DraftNode

    settings = _settings()
    dep = _deps(settings=settings, llm_responses=[_DRAFT_TEXT])
    ctx = ProcessingContext(
        invoice_match_result=InvoiceMatchResult.NOT_FOUND,
        invoice=None,
        requires_hitl=False,
        deps=dep,
        ticket=Ticket(
            thread_id="t-dn",
            message_id="m-dn",
            sender_email="billing@acme-supplies.com",
            subject="test",
            body="test",
            received_at=datetime.now(UTC),
        ),
    )
    node = DraftNode(context=ctx)
    result_ctx = await node.process(ctx)
    assert result_ctx.draft is not None
    assert result_ctx.draft.target == DraftTarget.INVOICING


@pytest.mark.asyncio
async def test_draft_node_hitl_path_no_draft():
    from app.domain.context import ProcessingContext
    from app.domain.enums import InvoiceMatchResult
    from app.workflow.nodes.draft import DraftNode

    dep = _deps(llm_responses=[])
    ctx = ProcessingContext(
        invoice_match_result=InvoiceMatchResult.MULTIPLE_OR_PARTIAL,
        invoice=None,
        requires_hitl=True,
        deps=dep,
        ticket=Ticket(
            thread_id="t-dn2",
            message_id="m-dn2",
            sender_email="billing@acme-supplies.com",
            subject="test",
            body="test",
            received_at=datetime.now(UTC),
        ),
    )
    node = DraftNode(context=ctx)
    result_ctx = await node.process(ctx)
    assert result_ctx.draft is None
