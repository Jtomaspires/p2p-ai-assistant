"""SQLModel repository adapters for PostgreSQL (also testable with SQLite)."""

from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from app.adapters.db_models import (
    AuditEntryTable,
    HumanReviewTable,
    InvoiceTable,
    ResponseDraftTable,
    RoutingRuleTable,
    SenderTable,
    TicketTable,
)
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
from app.domain.models import (
    AuditEntry,
    HumanReview,
    Invoice,
    ResponseDraft,
    RoutingRule,
    Sender,
    Ticket,
)
from app.ports.audit_port import AuditPort
from app.ports.draft_port import DraftPort
from app.ports.invoice_store_port import InvoiceStorePort
from app.ports.sender_directory_port import SenderDirectoryPort
from app.workflow.utils.normalise import normalize_reference


def _ticket_to_table(ticket: Ticket) -> TicketTable:
    return TicketTable(
        id=ticket.id,
        thread_id=ticket.thread_id,
        message_id=ticket.message_id,
        sender_email=ticket.sender_email,
        subject=ticket.subject,
        body=ticket.body,
        received_at=ticket.received_at,
        status=ticket.status.value,
        intent=ticket.intent.value if ticket.intent else None,
        language=ticket.language,
        assigned_operator_id=ticket.assigned_operator_id,
        confidence=ticket.confidence,
        is_thread_continuation=ticket.is_thread_continuation,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def _ticket_from_table(row: TicketTable) -> Ticket:
    return Ticket(
        id=row.id,
        thread_id=row.thread_id,
        message_id=row.message_id,
        sender_email=row.sender_email,
        subject=row.subject,
        body=row.body,
        received_at=row.received_at,
        status=TicketStatus(row.status),
        intent=Intent(row.intent) if row.intent else None,
        language=row.language,
        assigned_operator_id=row.assigned_operator_id,
        confidence=row.confidence,
        is_thread_continuation=row.is_thread_continuation,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class TicketRepo(InvoiceStorePort):
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, ticket: Ticket) -> Ticket:
        return self.save_ticket(ticket)

    def get_by_message_id(self, message_id: str) -> Ticket | None:
        row = self.session.exec(
            select(TicketTable).where(TicketTable.message_id == message_id)
        ).first()
        return _ticket_from_table(row) if row else None

    def get_by_thread_id(self, thread_id: str) -> Ticket | None:
        row = self.session.exec(
            select(TicketTable)
            .where(TicketTable.thread_id == thread_id)
            .order_by(TicketTable.updated_at.desc())
        ).first()
        return _ticket_from_table(row) if row else None

    def list_by_thread_id(self, thread_id: str) -> list[Ticket]:
        rows = self.session.exec(
            select(TicketTable)
            .where(TicketTable.thread_id == thread_id)
            .order_by(TicketTable.updated_at.desc())
        ).all()
        return [_ticket_from_table(row) for row in rows]

    def get_by_id(self, ticket_id: UUID) -> Ticket | None:
        row = self.session.get(TicketTable, ticket_id)
        return _ticket_from_table(row) if row else None

    def save_ticket(self, ticket: Ticket) -> Ticket:
        self.session.merge(_ticket_to_table(ticket))
        self.session.commit()
        return ticket

    def update_status(self, ticket_id: UUID, status: TicketStatus) -> Ticket | None:
        ticket = self.get_by_id(ticket_id)
        if ticket is None:
            return None
        ticket.status = status
        return self.save_ticket(ticket)

    def list_tickets(
        self,
        status: str | None = None,
        assigned_operator_id: str | None = None,
    ) -> list[Ticket]:
        statement = select(TicketTable)
        if status is not None:
            statement = statement.where(TicketTable.status == status)
        if assigned_operator_id is not None:
            statement = statement.where(
                TicketTable.assigned_operator_id == assigned_operator_id
            )
        statement = statement.order_by(TicketTable.received_at.desc())
        return [_ticket_from_table(row) for row in self.session.exec(statement).all()]

    def count_by_status(self) -> dict[str, int]:
        counts = {member.value: 0 for member in TicketStatus}
        rows = self.session.exec(
            select(TicketTable.status, func.count(TicketTable.id)).group_by(TicketTable.status)
        ).all()
        for status, n in rows:
            counts[str(status)] = int(n)
        return counts


def _sender_from_table(row: SenderTable) -> Sender:
    return Sender(
        id=row.id,
        email=row.email,
        name=row.name,
        company=row.company,
        vendor_sap_id=row.vendor_sap_id,
        sender_type=SenderType(row.sender_type),
        created_at=row.created_at,
    )


def _rule_from_table(row: RoutingRuleTable) -> RoutingRule:
    return RoutingRule(
        id=row.id,
        operator_id=row.operator_id,
        email=row.email,
        domain=row.domain,
    )


class SenderDirectoryRepo(SenderDirectoryPort):
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_sender(self, sender: Sender) -> Sender:
        self.session.merge(
            SenderTable(
                id=sender.id,
                email=sender.email.lower(),
                name=sender.name,
                company=sender.company,
                vendor_sap_id=sender.vendor_sap_id,
                sender_type=sender.sender_type.value,
                created_at=sender.created_at,
            )
        )
        self.session.commit()
        return sender

    def upsert_routing_rule(self, rule: RoutingRule) -> RoutingRule:
        self.session.merge(
            RoutingRuleTable(
                id=rule.id,
                operator_id=rule.operator_id,
                email=rule.email.lower() if rule.email else None,
                domain=rule.domain.lower() if rule.domain else None,
            )
        )
        self.session.commit()
        return rule

    def get_by_email(self, email: str) -> Sender | None:
        row = self.session.exec(
            select(SenderTable).where(SenderTable.email == email.lower())
        ).first()
        return _sender_from_table(row) if row else None

    def get_by_domain(self, domain: str) -> list[Sender]:
        suffix = f"@{domain.lower()}"
        rows = self.session.exec(
            select(SenderTable).where(SenderTable.email.endswith(suffix))
        ).all()
        return [_sender_from_table(row) for row in rows]

    def get_routing_rule_by_email(self, email: str) -> RoutingRule | None:
        row = self.session.exec(
            select(RoutingRuleTable).where(RoutingRuleTable.email == email.lower())
        ).first()
        return _rule_from_table(row) if row else None

    def get_routing_rule_by_domain(self, domain: str) -> RoutingRule | None:
        row = self.session.exec(
            select(RoutingRuleTable).where(RoutingRuleTable.domain == domain.lower())
        ).first()
        return _rule_from_table(row) if row else None


def _invoice_from_table(row: InvoiceTable) -> Invoice:
    return Invoice(
        invoice_ref=row.invoice_ref,
        supplier_name=row.supplier_name,
        amount=row.amount,
        stage=InvoiceStage(row.stage),
        currency=row.currency,
        status=InvoiceStatus(row.status) if row.status else None,
        sap_id=row.sap_id,
        company_code=row.company_code,
        payment_blocking_reason=row.payment_blocking_reason,
        approval_step=row.approval_step,
        due_date=row.due_date,
        approval_owner_email=row.approval_owner_email,
        clearing_document=row.clearing_document,
        payment_document=row.payment_document,
        payment_date=row.payment_date,
        payment_proof_ref=row.payment_proof_ref,
    )


class InvoiceRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, invoice: Invoice) -> Invoice:
        statement = select(InvoiceTable).where(
            InvoiceTable.invoice_ref == invoice.invoice_ref,
            InvoiceTable.stage == invoice.stage.value,
        )
        row = self.session.exec(statement).first() or InvoiceTable(
            invoice_ref=invoice.invoice_ref,
            supplier_invoice_ref_normalized=normalize_reference(invoice.invoice_ref),
            supplier_name=invoice.supplier_name,
            amount=invoice.amount,
            stage=invoice.stage.value,
        )
        row.supplier_invoice_ref_normalized = normalize_reference(invoice.invoice_ref)
        row.supplier_name = invoice.supplier_name
        row.amount = invoice.amount
        row.currency = invoice.currency
        row.status = invoice.status.value if invoice.status else None
        row.sap_id = invoice.sap_id
        row.company_code = invoice.company_code
        row.payment_blocking_reason = invoice.payment_blocking_reason
        row.approval_step = invoice.approval_step
        row.due_date = invoice.due_date
        row.approval_owner_email = invoice.approval_owner_email
        row.clearing_document = invoice.clearing_document
        row.payment_document = invoice.payment_document
        row.payment_date = invoice.payment_date
        row.payment_proof_ref = invoice.payment_proof_ref
        self.session.add(row)
        self.session.commit()
        return invoice

    def get_by_ref_normalized(self, reference: str) -> list[Invoice]:
        rows = self.session.exec(
            select(InvoiceTable).where(
                InvoiceTable.supplier_invoice_ref_normalized
                == normalize_reference(reference)
            )
        ).all()
        return [_invoice_from_table(row) for row in rows]

    def get_all_by_stage(self, stage: InvoiceStage) -> list[Invoice]:
        rows = self.session.exec(
            select(InvoiceTable).where(InvoiceTable.stage == stage.value)
        ).all()
        return [_invoice_from_table(row) for row in rows]


class AuditRepo(AuditPort):
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, entry: AuditEntry) -> None:
        self.session.add(
            AuditEntryTable(
                id=entry.id,
                ticket_id=entry.ticket_id,
                node=entry.node,
                action=entry.action.value,
                confidence=entry.confidence,
                audit_metadata=entry.metadata,
                created_at=entry.created_at,
            )
        )
        self.session.commit()

    def get_by_ticket_id(self, ticket_id: UUID) -> list[AuditEntry]:
        rows = self.session.exec(
            select(AuditEntryTable)
            .where(AuditEntryTable.ticket_id == ticket_id)
            .order_by(AuditEntryTable.created_at)
        ).all()
        return [
            AuditEntry(
                id=row.id,
                ticket_id=row.ticket_id,
                node=row.node,
                action=AuditAction(row.action),
                confidence=row.confidence,
                metadata=row.audit_metadata,
                created_at=row.created_at,
            )
            for row in rows
        ]


class DraftRepo(DraftPort):
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, draft: ResponseDraft) -> ResponseDraft:
        return self.save_draft(draft)

    def save_draft(self, draft: ResponseDraft) -> ResponseDraft:
        self.session.merge(
            ResponseDraftTable(
                id=draft.id,
                ticket_id=draft.ticket_id,
                target=draft.target.value,
                to_email=draft.to_email,
                generated_text=draft.generated_text,
                final_text=draft.final_text,
                edited_by_human=draft.edited_by_human,
                operator_notes=draft.operator_notes,
                attach_invoice_pdf=draft.attach_invoice_pdf,
                attach_payment_proof=draft.attach_payment_proof,
                created_at=draft.created_at,
            )
        )
        self.session.commit()
        return draft

    def get_by_ticket_id(self, ticket_id: UUID) -> ResponseDraft | None:
        row = self.session.exec(
            select(ResponseDraftTable)
            .where(ResponseDraftTable.ticket_id == ticket_id)
            .order_by(ResponseDraftTable.created_at.desc())
        ).first()
        if row is None:
            return None
        return ResponseDraft(
            id=row.id,
            ticket_id=row.ticket_id,
            target=DraftTarget(row.target),
            to_email=row.to_email,
            generated_text=row.generated_text,
            final_text=row.final_text,
            edited_by_human=row.edited_by_human,
            operator_notes=row.operator_notes,
            attach_invoice_pdf=row.attach_invoice_pdf,
            attach_payment_proof=row.attach_payment_proof,
            created_at=row.created_at,
        )

    def update_final_text(self, draft_id: UUID, final_text: str) -> ResponseDraft | None:
        row = self.session.get(ResponseDraftTable, draft_id)
        if row is None:
            return None
        row.final_text = final_text
        row.edited_by_human = True
        self.session.add(row)
        self.session.commit()
        return self.get_by_ticket_id(row.ticket_id)


class HumanReviewRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, review: HumanReview) -> HumanReview:
        self.session.add(
            HumanReviewTable(
                id=review.id,
                ticket_id=review.ticket_id,
                draft_id=review.draft_id,
                action=review.action.value,
                operator_id=review.operator_id,
                notes=review.notes,
                created_at=review.created_at,
            )
        )
        self.session.commit()
        return review

    def get_by_ticket_id(self, ticket_id: UUID) -> list[HumanReview]:
        rows = self.session.exec(
            select(HumanReviewTable).where(HumanReviewTable.ticket_id == ticket_id)
        ).all()
        return [
            HumanReview(
                id=row.id,
                ticket_id=row.ticket_id,
                draft_id=row.draft_id,
                action=HumanReviewAction(row.action),
                operator_id=row.operator_id,
                notes=row.notes,
                created_at=row.created_at,
            )
            for row in rows
        ]
