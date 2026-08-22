"""Node 8 — Send approved draft (Fase 3.8).

Not on the default ingest path. Used when an operator approves via the dashboard (Day 3 API)
or as a manual re-entry.  v1: NYLAS_SEND_ENABLED=False — marks ticket RESOLVED, no email sent.
"""

from datetime import UTC, datetime

from app.domain.context import ProcessingContext
from app.domain.enums import AuditAction, HumanReviewAction, TicketStatus
from app.domain.models import HumanReview
from app.domain.results import NodeResult
from app.workflow.core.base import Node
from app.workflow.nodes._helpers import finish, require_deps


class SendNode(Node):
    """Mark ticket as RESOLVED after operator approval; send email if enabled."""

    def __init__(
        self,
        context: ProcessingContext | None = None,
        operator_id: str | None = None,
        review_action: HumanReviewAction = HumanReviewAction.APPROVED,
        final_text: str | None = None,
        operator_notes: str | None = None,
    ) -> None:
        super().__init__(context=context)
        self.operator_id = operator_id
        self.review_action = review_action
        self.final_text = final_text
        self.operator_notes = operator_notes

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        self.context = context
        deps = require_deps(context)
        ticket = context.ticket
        draft = context.draft

        if ticket is None:
            return finish(context, NodeResult(action=AuditAction.SEND, stop_pipeline=True))

        op_id = self.operator_id or deps.settings.DEFAULT_OPERATOR_ID

        if draft is not None:
            if self.final_text is not None:
                draft.final_text = self.final_text
                draft.edited_by_human = True
            elif draft.final_text is None:
                draft.final_text = draft.generated_text
            if self.operator_notes:
                draft.operator_notes = self.operator_notes
            deps.drafts.save_draft(draft)

        send_mode = "mock"
        if deps.settings.NYLAS_SEND_ENABLED and draft is not None:
            send_mode = "nylas"

        ticket.status = TicketStatus.RESOLVED
        ticket.updated_at = datetime.now(UTC)
        deps.tickets.save_ticket(ticket)

        if draft is not None:
            human_review = HumanReview(
                ticket_id=ticket.id,
                draft_id=draft.id,
                action=self.review_action,
                operator_id=op_id,
                notes=self.operator_notes,
            )
            context.metadata["human_review"] = human_review.model_dump(mode="json")

        result = NodeResult(
            action=AuditAction.SEND,
            confidence=1.0,
            metadata={
                "send_mode": send_mode,
                "operator_id": op_id,
                "review_action": self.review_action.value,
            },
        )
        self.save_output(result)
        return finish(context, result)
