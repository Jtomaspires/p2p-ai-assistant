"""Dashboard ticket endpoints (Fase 4.1)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.adapters.mock_sap import MockSAPAdapter
from app.adapters.mock_senders import MockSenderDirectory
from app.adapters.postgres_repos import AuditRepo, DraftRepo, TicketRepo
from app.api.deps import get_session
from app.api.hitl import HitlService
from app.api.schemas import (
    ApproveBody,
    AuditSummary,
    EscalateBody,
    HitlActionResult,
    TicketDetail,
    TicketListItem,
)
from app.domain.enums import AuditAction, TicketStatus
from app.domain.models import Invoice, Sender, Ticket

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]


def _ticket_dump(ticket: Ticket) -> dict:
    return ticket.model_dump(mode="json")


def _sender_for(ticket: Ticket) -> Sender | None:
    return MockSenderDirectory().get_by_email(ticket.sender_email)


def _list_item(ticket: Ticket) -> TicketListItem:
    sender = _sender_for(ticket)
    return TicketListItem(
        id=ticket.id,
        received_at=ticket.received_at,
        sender_email=ticket.sender_email,
        sender_name=sender.name if sender else None,
        sender_company=sender.company if sender else None,
        subject=ticket.subject,
        intent=ticket.intent.value if ticket.intent else None,
        status=ticket.status.value,
        confidence=ticket.confidence,
        assigned_operator_id=ticket.assigned_operator_id,
    )


def _invoice_for_ticket(session: Session, ticket_id: UUID) -> Invoice | None:
    entries = AuditRepo(session).get_by_ticket_id(ticket_id)
    invoice_ref: str | None = None
    for entry in reversed(entries):
        if entry.action is AuditAction.RESOLVE:
            ref = entry.metadata.get("invoice_ref")
            if isinstance(ref, str) and ref:
                invoice_ref = ref
                break
    if invoice_ref is None:
        return None
    for invoice in MockSAPAdapter().invoices:
        if invoice.invoice_ref == invoice_ref:
            return invoice
    return None


@router.get("/tickets", response_model=list[TicketListItem])
def list_tickets(
    session: SessionDep,
    status: str | None = Query(default=None),
    assigned_operator_id: str | None = Query(default=None),
) -> list[TicketListItem]:
    if status is not None:
        valid = {member.value for member in TicketStatus}
        if status not in valid:
            raise HTTPException(status_code=422, detail="invalid status")
    tickets = TicketRepo(session).list_tickets(
        status=status,
        assigned_operator_id=assigned_operator_id,
    )
    return [_list_item(ticket) for ticket in tickets]


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
def get_ticket(ticket_id: UUID, session: SessionDep) -> TicketDetail:
    ticket = TicketRepo(session).get_by_id(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    draft = DraftRepo(session).get_by_ticket_id(ticket_id)
    sender = _sender_for(ticket)
    invoice = _invoice_for_ticket(session, ticket_id)
    audit = [
        AuditSummary(
            node=entry.node,
            action=entry.action.value,
            confidence=entry.confidence,
            created_at=entry.created_at,
        )
        for entry in AuditRepo(session).get_by_ticket_id(ticket_id)
    ]
    return TicketDetail(
        ticket=_ticket_dump(ticket),
        sender=sender.model_dump(mode="json") if sender else None,
        draft=draft.model_dump(mode="json") if draft else None,
        invoice=invoice.model_dump(mode="json") if invoice else None,
        audit=audit,
    )


@router.get("/tickets/{ticket_id}/draft")
def get_draft(ticket_id: UUID, session: SessionDep) -> dict:
    if TicketRepo(session).get_by_id(ticket_id) is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    draft = DraftRepo(session).get_by_ticket_id(ticket_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    return draft.model_dump(mode="json")


@router.post("/tickets/{ticket_id}/approve", response_model=HitlActionResult)
async def approve_ticket(
    ticket_id: UUID,
    body: ApproveBody,
    session: SessionDep,
) -> HitlActionResult:
    ticket, draft, review = await HitlService(session).approve(
        ticket_id=ticket_id,
        operator_id=body.operator_id,
        final_text=body.final_text,
    )
    return HitlActionResult(
        ticket=_ticket_dump(ticket),
        draft=draft.model_dump(mode="json"),
        human_review=review.model_dump(mode="json"),
    )


@router.post("/tickets/{ticket_id}/escalate", response_model=HitlActionResult)
def escalate_ticket(
    ticket_id: UUID,
    body: EscalateBody,
    session: SessionDep,
) -> HitlActionResult:
    ticket, draft, review = HitlService(session).escalate(
        ticket_id=ticket_id,
        operator_id=body.operator_id,
    )
    return HitlActionResult(
        ticket=_ticket_dump(ticket),
        draft=draft.model_dump(mode="json"),
        human_review=review.model_dump(mode="json"),
    )


@router.get("/stats")
def stats(session: SessionDep) -> dict[str, int]:
    return TicketRepo(session).count_by_status()
