"""Test Gate 1 — domain enums and Pydantic models."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.domain.context import ProcessingContext
from app.domain.enums import (
    AuditAction,
    DraftTarget,
    HumanReviewAction,
    Intent,
    InvoiceMatchResult,
    InvoiceStage,
    InvoiceStatus,
    SenderType,
    TicketStatus,
)
from app.domain.models import (
    AuditEntry,
    HumanReview,
    Invoice,
    ResponseDraft,
    RoutingRule,
    Sender,
    Ticket,
)
from app.domain.results import NodeResult


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


def test_ticket_status_members():
    assert TicketStatus.QUARANTINED.value == "quarantined"
    assert {member.value for member in TicketStatus} == {
        "open",
        "awaiting_human",
        "awaiting_sender_reply",
        "resolved",
        "escalated",
        "quarantined",
        "discarded",
        "delegated",
    }


def test_intent_members():
    assert {member.value for member in Intent} == {
        "payment_status",
        "delay_reason",
        "future_timing",
        "unknown",
    }


def test_sender_type_members():
    assert SenderType.EXTERNAL_SUPPLIER.value == "external_supplier"
    assert {member.value for member in SenderType} == {
        "external_supplier",
        "internal_shareholder",
        "group_p2p",
        "unknown",
    }


def test_invoice_stage_and_status_members():
    assert InvoiceStage.IN_APPROVAL.value == "in_approval"
    assert InvoiceStage.POSTED.value == "posted"
    assert {member.value for member in InvoiceStatus} == {
        "pending_payment",
        "partially_paid",
        "paid",
        "blocked",
    }


def test_invoice_match_result_members():
    assert InvoiceMatchResult.NOT_FOUND.value == "not_found"
    assert {member.value for member in InvoiceMatchResult} == {
        "not_found",
        "unique",
        "vat_discrepancy",
        "multiple_or_partial",
        "too_many",
    }


def test_draft_target_members():
    assert {member.value for member in DraftTarget} == {
        "sender",
        "invoicing",
        "approval_owners",
        "payments",
    }


def test_human_review_action_members():
    assert {member.value for member in HumanReviewAction} == {
        "approved",
        "approved_with_edit",
        "escalated_to_email",
    }


def test_audit_action_members():
    assert AuditAction.PASS.value == "pass"
    assert {member.value for member in AuditAction} == {
        "pass",
        "quarantine",
        "ingest",
        "thread",
        "discard",
        "classify",
        "identify",
        "mine",
        "delegate",
        "resolve",
        "draft",
        "hitl",
        "approve",
        "approve_edit",
        "escalate",
        "send",
    }


def test_ticket_validates_with_required_fields():
    ticket = _ticket()
    assert ticket.thread_id == "thread-1"
    assert ticket.status is TicketStatus.OPEN
    assert isinstance(ticket.id, UUID)


def test_ticket_rejects_missing_thread_id():
    with pytest.raises(ValidationError):
        Ticket(
            message_id="msg-1",
            sender_email="billing@acme-supplies.com",
            subject="Invoice",
            body="Hello",
            received_at=datetime(2026, 8, 21, tzinfo=UTC),
        )


def test_invoice_in_approval_allows_null_status():
    invoice = Invoice(
        invoice_ref="INV-2026-0008",
        supplier_name="ACME Supplies Lda",
        amount=Decimal("6150.00"),
        stage=InvoiceStage.IN_APPROVAL,
        status=None,
    )
    assert invoice.status is None
    assert invoice.stage is InvoiceStage.IN_APPROVAL


def test_invoice_posted_paid():
    invoice = Invoice(
        invoice_ref="INV-2026-0005",
        supplier_name="ACME Supplies Lda",
        amount=Decimal("14760.00"),
        stage=InvoiceStage.POSTED,
        status=InvoiceStatus.PAID,
        clearing_document="1400000123",
    )
    assert invoice.status is InvoiceStatus.PAID


def test_response_draft_defaults():
    draft = ResponseDraft(
        ticket_id=uuid4(),
        target=DraftTarget.SENDER,
        to_email="billing@acme-supplies.com",
        generated_text="Your invoice is pending payment.",
    )
    assert draft.edited_by_human is False
    assert draft.attach_invoice_pdf is False
    assert draft.attach_payment_proof is False


def test_processing_context_requires_only_ticket():
    context = ProcessingContext(ticket=_ticket())
    assert context.sender is None
    assert context.should_stop is False
    assert context.invoice is None
    assert context.draft is None
    assert context.extracted_ref is None
    assert context.extracted_amount is None
    assert context.is_thread_continuation is False
    assert context.confidence_components == {}


def test_node_result_defaults_do_not_stop_pipeline():
    result = NodeResult(action=AuditAction.PASS)
    assert result.stop_pipeline is False
    assert result.confidence is None
    assert result.metadata == {}


def test_ticket_serialisation_round_trip():
    original = _ticket(intent=Intent.PAYMENT_STATUS, confidence=0.91)
    restored = Ticket.model_validate(original.model_dump())
    assert restored == original


def test_sender_and_routing_rule_instantiate():
    sender = Sender(
        id="s-1",
        email="billing@acme-supplies.com",
        name="Maria Costa",
        company="ACME Supplies Lda",
        vendor_sap_id="10300006",
        sender_type=SenderType.EXTERNAL_SUPPLIER,
    )
    rule = RoutingRule(
        id="R1",
        domain="group-subsidiary.com",
        operator_id="op_ana",
    )
    assert sender.vendor_sap_id == "10300006"
    assert rule.email is None


def test_audit_entry_and_human_review_instantiate():
    ticket_id = uuid4()
    draft_id = uuid4()
    entry = AuditEntry(
        ticket_id=ticket_id,
        node="security",
        action=AuditAction.QUARANTINE,
        metadata={"reason": "spf_fail"},
    )
    review = HumanReview(
        ticket_id=ticket_id,
        draft_id=draft_id,
        action=HumanReviewAction.APPROVED,
        operator_id="op_joao",
    )
    assert entry.node == "security"
    assert review.notes is None
