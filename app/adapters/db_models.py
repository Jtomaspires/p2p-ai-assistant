"""SQLModel persistence tables kept separate from Pydantic domain models."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON, Numeric, Text
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TicketTable(SQLModel, table=True):
    __tablename__ = "tickets"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    thread_id: str = Field(index=True)
    message_id: str = Field(index=True, unique=True)
    sender_email: str = Field(index=True)
    subject: str
    body: str = Field(sa_column=Column(Text, nullable=False))
    received_at: datetime
    status: str = Field(index=True)
    intent: str | None = None
    language: str | None = None
    assigned_operator_id: str | None = Field(default=None, index=True)
    confidence: float | None = None
    is_thread_continuation: bool = False
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class SenderTable(SQLModel, table=True):
    __tablename__ = "senders"

    id: str = Field(primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str
    company: str
    vendor_sap_id: str | None = Field(default=None, index=True)
    sender_type: str
    created_at: datetime = Field(default_factory=_utc_now)


class RoutingRuleTable(SQLModel, table=True):
    __tablename__ = "routing_rules"

    id: str = Field(primary_key=True)
    operator_id: str
    email: str | None = Field(default=None, index=True)
    domain: str | None = Field(default=None, index=True)


class InvoiceTable(SQLModel, table=True):
    __tablename__ = "invoice_cache"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    invoice_ref: str = Field(index=True)
    supplier_invoice_ref_normalized: str = Field(index=True)
    supplier_name: str = Field(index=True)
    amount: Decimal = Field(sa_column=Column(Numeric(18, 2), nullable=False))
    stage: str = Field(index=True)
    currency: str = "EUR"
    status: str | None = Field(default=None, index=True)
    sap_id: str | None = Field(default=None, index=True)
    company_code: str | None = None
    payment_blocking_reason: str | None = None
    approval_step: str | None = None
    due_date: date | None = None
    approval_owner_email: str | None = None
    clearing_document: str | None = None
    payment_document: str | None = None
    payment_date: date | None = None
    payment_proof_ref: str | None = None


class ResponseDraftTable(SQLModel, table=True):
    __tablename__ = "response_drafts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    ticket_id: UUID = Field(foreign_key="tickets.id", index=True)
    target: str
    to_email: str
    generated_text: str = Field(sa_column=Column(Text, nullable=False))
    final_text: str | None = Field(default=None, sa_column=Column(Text))
    edited_by_human: bool = False
    operator_notes: str | None = Field(default=None, sa_column=Column(Text))
    attach_invoice_pdf: bool = False
    attach_payment_proof: bool = False
    created_at: datetime = Field(default_factory=_utc_now)


class AuditEntryTable(SQLModel, table=True):
    __tablename__ = "audit_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    ticket_id: UUID = Field(foreign_key="tickets.id", index=True)
    node: str = Field(index=True)
    action: str = Field(index=True)
    confidence: float | None = None
    audit_metadata: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utc_now)


class HumanReviewTable(SQLModel, table=True):
    __tablename__ = "human_reviews"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    ticket_id: UUID = Field(foreign_key="tickets.id", index=True)
    draft_id: UUID = Field(foreign_key="response_drafts.id", index=True)
    action: str
    operator_id: str = Field(index=True)
    notes: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=_utc_now)
