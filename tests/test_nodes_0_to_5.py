"""Test Gate 2 — nodes 0–5 (Launchpad-style classes, Day 0 fixtures)."""

from datetime import UTC, datetime

import pytest

from app.adapters.memory_audit import InMemoryAuditLog
from app.adapters.memory_ticket_store import InMemoryTicketStore
from app.adapters.mock_email import MockEmailAdapter
from app.adapters.mock_llm import MockLLMAdapter
from app.adapters.mock_sap import MockSAPAdapter
from app.adapters.mock_senders import MockSenderDirectory
from app.domain.context import ProcessingContext
from app.domain.deps import WorkflowDeps
from app.domain.enums import AuditAction, Intent, TicketStatus
from app.domain.events import IncomingEmail
from app.domain.models import Ticket
from app.workflow.core.base import BaseRouter, Node, RouterNode
from app.workflow.nodes.ingestion import IngestionNode
from app.workflow.nodes.intent import IntentNode
from app.workflow.nodes.routing import RoutingNode
from app.workflow.nodes.security import SecurityNode
from app.workflow.nodes.sender import SenderIdNode
from app.workflow.nodes.thread import ThreadResolutionNode
from app.workflow.nodes.triage import TriageNode
from app.workflow.ticket_workflow import TicketWorkflow
from settings import Settings


def _settings(**overrides) -> Settings:
    payload = {
        "_env_file": None,
        "DATABASE_URL": "sqlite://",
        "NYLAS_SEND_ENABLED": False,
        "SPF_DKIM_ENABLED": False,
        "SECURITY_CHECK_ENABLED": False,
    }
    payload.update(overrides)
    return Settings(**payload)


def _deps(settings: Settings | None = None, llm_responses: list | None = None) -> WorkflowDeps:
    return WorkflowDeps(
        settings=settings or _settings(),
        llm=MockLLMAdapter(llm_responses or []),
        email=MockEmailAdapter(),
        tickets=InMemoryTicketStore(),
        sap=MockSAPAdapter(),
        audit=InMemoryAuditLog(),
        senders=MockSenderDirectory(),
    )


def _ticket(**overrides) -> Ticket:
    payload = {
        "thread_id": "thread-1",
        "message_id": "msg-1",
        "sender_email": "billing@acme-supplies.com",
        "subject": "Invoice INV-2026-0001",
        "body": "Please confirm payment status.",
        "received_at": datetime(2026, 8, 21, tzinfo=UTC),
    }
    payload.update(overrides)
    return Ticket.model_validate(payload)


def _context(deps: WorkflowDeps, ticket: Ticket | None = None, **kwargs) -> ProcessingContext:
    return ProcessingContext(ticket=ticket, deps=deps, **kwargs)


async def _run(node, context: ProcessingContext):
    node.context = context
    return await node.process(context)


# --- Node 0 security ---


@pytest.mark.asyncio
async def test_security_pass_when_disabled():
    deps = _deps()
    ctx = _context(deps, _ticket(), event=IncomingEmail(from_email="billing@acme-supplies.com", thread_id="t", message_id="m"))
    ctx = await _run(SecurityNode(), ctx)
    assert ctx.last_result.action is AuditAction.PASS
    assert ctx.should_stop is False
    assert ctx.ticket.status is TicketStatus.OPEN


@pytest.mark.asyncio
async def test_security_whitelist_pass():
    deps = _deps(_settings(SECURITY_CHECK_ENABLED=True))
    ctx = _context(
        deps,
        _ticket(),
        event=IncomingEmail(from_email="billing@acme-supplies.com", thread_id="t", message_id="m"),
    )
    ctx = await _run(SecurityNode(), ctx)
    assert ctx.last_result.action is AuditAction.PASS
    assert ctx.ticket.status is TicketStatus.OPEN


@pytest.mark.asyncio
async def test_security_unknown_domain_quarantines():
    deps = _deps(_settings(SECURITY_CHECK_ENABLED=True))
    ctx = _context(
        deps,
        _ticket(sender_email="spoof@evil.example"),
        event=IncomingEmail(from_email="spoof@evil.example", thread_id="t", message_id="m"),
    )
    ctx = await _run(SecurityNode(), ctx)
    assert ctx.last_result.action is AuditAction.QUARANTINE
    assert ctx.last_result.stop_pipeline is True
    assert ctx.ticket.status is TicketStatus.QUARANTINED
    assert ctx.should_stop is True


# --- Node 1 ingest ---


@pytest.mark.asyncio
async def test_ingest_valid_payload_populates_ticket():
    deps = _deps()
    ctx = ProcessingContext(
        deps=deps,
        event=IncomingEmail(
            thread_id="nylas-thread-1",
            message_id="nylas-msg-1",
            from_email="billing@acme-supplies.com",
            subject="Invoice INV-2026-0001",
            body="Please pay",
            attachments=[{"filename": "INV-2026-0001.pdf"}],
        ),
    )
    ctx = await _run(IngestionNode(), ctx)
    assert ctx.last_result.action is AuditAction.INGEST
    assert ctx.ticket is not None
    assert ctx.ticket.thread_id == "nylas-thread-1"
    assert ctx.last_result.metadata["attachments"][0]["is_invoice"] is True


@pytest.mark.asyncio
async def test_ingest_duplicate_message_id_ignored():
    deps = _deps()
    original = _ticket(message_id="dup-1")
    deps.tickets.save_ticket(original)
    ctx = ProcessingContext(
        deps=deps,
        event=IncomingEmail(
            thread_id="thread-1",
            message_id="dup-1",
            from_email="billing@acme-supplies.com",
        ),
    )
    ctx = await _run(IngestionNode(), ctx)
    assert ctx.last_result.metadata["reason"] == "duplicate_ignored"
    assert ctx.last_result.stop_pipeline is True
    assert ctx.ticket.id == original.id


@pytest.mark.asyncio
async def test_ingest_missing_ids_rejected():
    deps = _deps()
    ctx = ProcessingContext(deps=deps, event=IncomingEmail(from_email="a@b.com", subject="hi"))
    ctx = await _run(IngestionNode(), ctx)
    assert ctx.last_result.metadata["reason"] == "ingest_rejected"
    assert ctx.ticket is None


# --- Node 1.5 thread ---


@pytest.mark.asyncio
async def test_thread_new_when_no_existing():
    deps = _deps()
    ctx = _context(deps, _ticket())
    ctx = await _run(ThreadResolutionNode(), ctx)
    assert ctx.is_thread_continuation is False
    assert ctx.last_result.metadata["outcome"] == "new_thread"


@pytest.mark.asyncio
async def test_thread_open_continuation_reuses_intent():
    deps = _deps()
    previous = _ticket(message_id="old", intent=Intent.PAYMENT_STATUS, status=TicketStatus.OPEN)
    deps.tickets.save_ticket(previous)
    incoming = _ticket(message_id="new-msg", body="Any update?")
    ctx = _context(deps, incoming)
    ctx = await _run(ThreadResolutionNode(), ctx)
    assert ctx.is_thread_continuation is True
    assert ctx.ticket.id == previous.id
    assert ctx.ticket.intent is Intent.PAYMENT_STATUS
    assert ctx.ticket.message_id == "new-msg"


@pytest.mark.asyncio
async def test_thread_escalated_keeps_status_and_stops():
    deps = _deps()
    previous = _ticket(message_id="old", status=TicketStatus.ESCALATED)
    deps.tickets.save_ticket(previous)
    ctx = _context(deps, _ticket(message_id="follow-up"))
    ctx = await _run(ThreadResolutionNode(), ctx)
    assert ctx.ticket.status is TicketStatus.ESCALATED
    assert ctx.last_result.stop_pipeline is True
    assert ctx.last_result.metadata["outcome"] == "continuation_escalated_keep"


# --- Node 2 triage ---


@pytest.mark.asyncio
async def test_triage_high_confidence_non_ap_discards():
    deps = _deps(llm_responses=[{"is_ap": False, "confidence": 0.9}])
    ctx = _context(deps, _ticket())
    ctx = await _run(TriageNode(), ctx)
    assert ctx.last_result.action is AuditAction.DISCARD
    assert ctx.last_result.stop_pipeline is True
    assert ctx.ticket.status is TicketStatus.DISCARDED
    assert isinstance(TriageNode(), BaseRouter)


@pytest.mark.asyncio
async def test_triage_low_confidence_non_ap_continues():
    deps = _deps(llm_responses=[{"is_ap": False, "confidence": 0.6}])
    ctx = _context(deps, _ticket())
    ctx = await _run(TriageNode(), ctx)
    assert ctx.last_result.action is AuditAction.CLASSIFY
    assert ctx.last_result.stop_pipeline is False
    assert ctx.ticket.status is TicketStatus.OPEN


# --- Node 3 intent ---


@pytest.mark.asyncio
async def test_intent_payment_status():
    deps = _deps(
        llm_responses=[
            {
                "intent": "payment_status",
                "confidence": 0.85,
                "language": "en",
                "extracted_ref": "INV-2026-0001",
                "extracted_amount": "12300.00",
                "extracted_date": None,
            }
        ]
    )
    ctx = _context(deps, _ticket())
    ctx = await _run(IntentNode(), ctx)
    assert ctx.ticket.intent is Intent.PAYMENT_STATUS
    assert ctx.extracted_ref == "INV-2026-0001"
    assert ctx.skip_identity is False
    assert isinstance(IntentNode(), BaseRouter)


@pytest.mark.asyncio
async def test_intent_low_confidence_does_not_stop():
    deps = _deps(
        llm_responses=[{"intent": "payment_status", "confidence": 0.3, "language": "en"}]
    )
    ctx = _context(deps, _ticket())
    ctx = await _run(IntentNode(), ctx)
    assert ctx.ticket.intent is Intent.UNKNOWN
    assert ctx.skip_identity is True
    assert ctx.last_result.stop_pipeline is False
    assert ctx.ticket.assigned_operator_id == deps.settings.DEFAULT_OPERATOR_ID
    assert IntentNode().route(ctx) is None


# --- Node 4 sender ---


@pytest.mark.asyncio
async def test_sender_email_match():
    deps = _deps()
    ctx = _context(deps, _ticket(sender_email="billing@acme-supplies.com"))
    ctx = await _run(SenderIdNode(), ctx)
    assert ctx.last_result.confidence == 0.9
    assert ctx.sender is not None
    assert ctx.sender.email == "billing@acme-supplies.com"


@pytest.mark.asyncio
async def test_sender_unique_domain_match():
    deps = _deps()
    ctx = _context(deps, _ticket(sender_email="ap@acme-supplies.com"))
    ctx = await _run(SenderIdNode(), ctx)
    assert ctx.last_result.confidence == 0.6
    assert ctx.sender is not None


@pytest.mark.asyncio
async def test_sender_unknown():
    deps = _deps()
    ctx = _context(deps, _ticket(sender_email="nobody@unknown.example"))
    ctx = await _run(SenderIdNode(), ctx)
    assert ctx.last_result.confidence == 0
    assert ctx.sender is None


# --- Node 5 routing ---


@pytest.mark.asyncio
async def test_routing_delegate_on_subsidiary_domain():
    deps = _deps()
    ctx = _context(deps, _ticket(sender_email="joao.silva@group-subsidiary.com"))
    ctx = await _run(RoutingNode(), ctx)
    assert ctx.last_result.action is AuditAction.DELEGATE
    assert ctx.last_result.stop_pipeline is True
    assert ctx.ticket.status is TicketStatus.DELEGATED
    assert ctx.ticket.assigned_operator_id == "op_ana"
    assert isinstance(RoutingNode(), BaseRouter)
    assert isinstance(RoutingNode.routes[0], RouterNode)


@pytest.mark.asyncio
async def test_routing_mine_when_no_rule():
    deps = _deps()
    ctx = _context(deps, _ticket(sender_email="billing@acme-supplies.com"))
    ctx = await _run(RoutingNode(), ctx)
    assert ctx.last_result.action is AuditAction.MINE
    assert ctx.ticket.assigned_operator_id == deps.settings.DEFAULT_OPERATOR_ID
    assert ctx.last_result.stop_pipeline is False


# --- Workflow wiring ---


@pytest.mark.asyncio
async def test_day1_workflow_happy_path():
    deps = _deps(
        llm_responses=[
            {"is_ap": True, "confidence": 0.92},
            {
                "intent": "payment_status",
                "confidence": 0.88,
                "language": "en",
                "extracted_ref": "INV-2026-0001",
                "extracted_amount": "12300.00",
            },
        ]
    )
    workflow = TicketWorkflow(deps)
    ctx = await workflow.run_async(
        {
            "thread_id": "wf-thread",
            "message_id": "wf-msg",
            "from_email": "billing@acme-supplies.com",
            "subject": "Payment status INV-2026-0001",
            "body": "When will invoice INV-2026-0001 be paid?",
        }
    )
    assert ctx.ticket is not None
    assert ctx.ticket.intent is Intent.PAYMENT_STATUS
    assert ctx.sender is not None
    assert ctx.last_result.action is AuditAction.MINE
    assert {entry.node for entry in deps.audit.entries} >= {
        "IngestionNode",
        "SecurityNode",
        "ThreadResolutionNode",
        "TriageNode",
        "IntentNode",
        "SenderIdNode",
        "RoutingNode",
    }


@pytest.mark.asyncio
async def test_day1_workflow_quarantine_stops_before_triage():
    deps = _deps(_settings(SECURITY_CHECK_ENABLED=True))
    workflow = TicketWorkflow(deps)
    ctx = await workflow.run_async(
        {
            "thread_id": "q-thread",
            "message_id": "q-msg",
            "from_email": "attacker@evil.example",
            "subject": "Invoice",
            "body": "pay now",
        }
    )
    assert ctx.ticket.status is TicketStatus.QUARANTINED
    assert all(entry.node != "TriageNode" for entry in deps.audit.entries)


def test_nodes_are_classes_not_functions():
    for cls in (SecurityNode, IngestionNode, ThreadResolutionNode, TriageNode, IntentNode, SenderIdNode, RoutingNode):
        assert issubclass(cls, Node)
