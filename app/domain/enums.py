"""Domain enumerations from Fase 2.2."""

from enum import Enum


class TicketStatus(str, Enum):
    OPEN = "open"
    AWAITING_HUMAN = "awaiting_human"
    AWAITING_SENDER_REPLY = "awaiting_sender_reply"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    QUARANTINED = "quarantined"
    DISCARDED = "discarded"
    DELEGATED = "delegated"


class Intent(str, Enum):
    PAYMENT_STATUS = "payment_status"
    DELAY_REASON = "delay_reason"
    FUTURE_TIMING = "future_timing"
    UNKNOWN = "unknown"


class SenderType(str, Enum):
    EXTERNAL_SUPPLIER = "external_supplier"
    INTERNAL_SHAREHOLDER = "internal_shareholder"
    GROUP_P2P = "group_p2p"
    UNKNOWN = "unknown"


class InvoiceStage(str, Enum):
    IN_APPROVAL = "in_approval"
    POSTED = "posted"


class InvoiceStatus(str, Enum):
    """Only meaningful when Invoice.stage == POSTED."""

    PENDING_PAYMENT = "pending_payment"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    BLOCKED = "blocked"


class InvoiceMatchResult(str, Enum):
    NOT_FOUND = "not_found"
    UNIQUE = "unique"
    VAT_DISCREPANCY = "vat_discrepancy"
    MULTIPLE_OR_PARTIAL = "multiple_or_partial"
    TOO_MANY = "too_many"


class DraftTarget(str, Enum):
    SENDER = "sender"
    INVOICING = "invoicing"
    APPROVAL_OWNERS = "approval_owners"
    PAYMENTS = "payments"


class HumanReviewAction(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_EDIT = "approved_with_edit"
    ESCALATED_TO_EMAIL = "escalated_to_email"


class AuditAction(str, Enum):
    PASS = "pass"
    QUARANTINE = "quarantine"
    INGEST = "ingest"
    THREAD = "thread"
    DISCARD = "discard"
    CLASSIFY = "classify"
    IDENTIFY = "identify"
    MINE = "mine"
    DELEGATE = "delegate"
    RESOLVE = "resolve"
    DRAFT = "draft"
    HITL = "hitl"
    APPROVE = "approve"
    APPROVE_EDIT = "approve_edit"
    ESCALATE = "escalate"
    SEND = "send"
