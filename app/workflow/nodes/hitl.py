"""Node 7 — Human-in-the-Loop stop (Fase 3.7).

Sets ticket status to AWAITING_HUMAN, persists the draft, and halts the pipeline.
Human acts via the operator dashboard (Day 3). SendNode is the re-entry point after approval.
"""

from app.domain.context import ProcessingContext
from app.domain.enums import AuditAction, TicketStatus
from app.domain.results import NodeResult
from app.workflow.core.base import Node
from app.workflow.nodes._helpers import finish, require_deps


class HitlNode(Node):
    """Stop the pipeline and hand off to a human operator."""

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        self.context = context
        deps = require_deps(context)
        ticket = context.ticket
        if ticket is None:
            return finish(context, NodeResult(action=AuditAction.HITL, stop_pipeline=True))

        ticket.status = TicketStatus.AWAITING_HUMAN
        deps.tickets.save_ticket(ticket)

        if context.draft is not None:
            deps.drafts.save_draft(context.draft)

        result = NodeResult(
            action=AuditAction.HITL,
            confidence=1.0,
            metadata={
                "draft_id": str(context.draft.id) if context.draft else None,
                "draft_target": context.draft.target.value if context.draft else None,
                "requires_hitl": context.requires_hitl,
            },
            stop_pipeline=True,
        )
        self.save_output(result)
        return finish(context, result)
