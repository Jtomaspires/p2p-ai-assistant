"""Persisted domain models from Fase 2."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.domain.enums import (
    AuditAction,
    DraftTarget,
    HumanReviewAction,
    Intent,
    InvoiceStage,
    InvoiceStatus,
    SenderType,
    TicketStatus,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Sender(BaseModel):
    id: str
    email: str
    name: str
    company: str
    vendor_sap_id: str | None = None
    sender_type: SenderType = SenderType.UNKNOWN
    created_at: datetime = Field(default_factory=_utc_now)


class RoutingRule(BaseModel):
    id: str
    operator_id: str
    email: str | None = None
    domain: str | None = None


class Ticket(BaseModel):
    thread_id: str
    message_id: str
    sender_email: str
    subject: str
    body: str
    received_at: datetime
    id: UUID = Field(default_factory=uuid4)
    status: TicketStatus = TicketStatus.OPEN
    intent: Intent | None = None
    language: str | None = None
    assigned_operator_id: str | None = None
    confidence: float | None = None
    is_thread_continuation: bool = False
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class Invoice(BaseModel):
    invoice_ref: str
    supplier_name: str
    amount: Decimal
    stage: InvoiceStage
    currency: str = "EUR"
    status: InvoiceStatus | None = None
    sap_id: str | None = None
    company_code: str | None = None
    payment_blocking_reason: str | None = None
    approval_step: str | None = None
    due_date: date | None = None
    approval_owner_email: str | None = None
    clearing_document: str | None = None
    payment_document: str | None = None
    payment_date: date | None = None
    payment_proof_ref: str | None = None


class ResponseDraft(BaseModel):
    ticket_id: UUID
    target: DraftTarget
    to_email: str
    generated_text: str
    id: UUID = Field(default_factory=uuid4)
    final_text: str | None = None
    edited_by_human: bool = False
    operator_notes: str | None = None
    attach_invoice_pdf: bool = False
    attach_payment_proof: bool = False
    created_at: datetime = Field(default_factory=_utc_now)


class AuditEntry(BaseModel):
    ticket_id: UUID
    node: str
    action: AuditAction
    id: UUID = Field(default_factory=uuid4)
    confidence: float | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class HumanReview(BaseModel):
    ticket_id: UUID
    draft_id: UUID
    action: HumanReviewAction
    operator_id: str
    id: UUID = Field(default_factory=uuid4)
    notes: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
