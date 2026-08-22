"""HITL approve / escalate actions used by dashboard API endpoints."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session

from app.adapters.postgres_repos import (
    AuditRepo,
    DraftRepo,
    HumanReviewRepo,
    TicketRepo,
)
from app.api.deps import build_workflow_deps
from app.domain.context import ProcessingContext
from app.domain.enums import AuditAction, HumanReviewAction, TicketStatus
from app.domain.models import AuditEntry, HumanReview, ResponseDraft, Ticket
from app.workflow.nodes.send import SendNode


class HitlService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.tickets = TicketRepo(session)
        self.drafts = DraftRepo(session)
        self.reviews = HumanReviewRepo(session)
        self.audit = AuditRepo(session)

    def _load_actionable(self, ticket_id: UUID) -> tuple[Ticket, ResponseDraft]:
        ticket = self.tickets.get_by_id(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="ticket not found")
        if ticket.status is not TicketStatus.AWAITING_HUMAN:
            raise HTTPException(
                status_code=409,
                detail="ticket is not awaiting human review",
            )
        draft = self.drafts.get_by_ticket_id(ticket_id)
        if draft is None:
            raise HTTPException(status_code=409, detail="ticket has no draft")
        return ticket, draft

    async def approve(
        self,
        ticket_id: UUID,
        operator_id: str,
        final_text: str | None,
    ) -> tuple[Ticket, ResponseDraft, HumanReview]:
        ticket, draft = self._load_actionable(ticket_id)
        edited = bool(final_text)
        review_action = (
            HumanReviewAction.APPROVED_WITH_EDIT if edited else HumanReviewAction.APPROVED
        )
        deps = build_workflow_deps(self.session)
        context = ProcessingContext(ticket=ticket, draft=draft, deps=deps)
        node = SendNode(
            context=context,
            operator_id=operator_id,
            review_action=review_action,
            final_text=final_text if edited else None,
        )
        context = await node.process(context)
        saved_ticket = context.ticket or ticket
        saved_draft = context.draft or draft

        review = HumanReview(
            ticket_id=saved_ticket.id,
            draft_id=saved_draft.id,
            action=review_action,
            operator_id=operator_id,
        )
        self.reviews.create(review)

        approve_action = AuditAction.APPROVE_EDIT if edited else AuditAction.APPROVE
        self.audit.append(
            AuditEntry(
                ticket_id=saved_ticket.id,
                node="HitlService",
                action=approve_action,
                confidence=1.0,
                metadata={"operator_id": operator_id},
            )
        )
        if context.last_result is not None:
            self.audit.append(
                AuditEntry(
                    ticket_id=saved_ticket.id,
                    node="SendNode",
                    action=context.last_result.action,
                    confidence=context.last_result.confidence,
                    metadata=context.last_result.metadata,
                )
            )
        return saved_ticket, saved_draft, review

    def escalate(
        self,
        ticket_id: UUID,
        operator_id: str,
    ) -> tuple[Ticket, ResponseDraft, HumanReview]:
        ticket, draft = self._load_actionable(ticket_id)
        ticket.status = TicketStatus.ESCALATED
        ticket.updated_at = datetime.now(UTC)
        self.tickets.save_ticket(ticket)

        review = HumanReview(
            ticket_id=ticket.id,
            draft_id=draft.id,
            action=HumanReviewAction.ESCALATED_TO_EMAIL,
            operator_id=operator_id,
        )
        self.reviews.create(review)
        self.audit.append(
            AuditEntry(
                ticket_id=ticket.id,
                node="HitlService",
                action=AuditAction.ESCALATE,
                confidence=1.0,
                metadata={"operator_id": operator_id},
            )
        )
        return ticket, draft, review
