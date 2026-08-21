"""Node 1.5 — thread resolution (Fase 3.1.5).

Acts as a BaseRouter so thread continuations skip Triage/Intent/Sender/Routing
and jump directly to ResolutionNode.
"""

from datetime import UTC, datetime

from app.domain.context import ProcessingContext
from app.domain.enums import AuditAction, TicketStatus
from app.domain.results import NodeResult
from app.workflow.core.base import BaseRouter, Node, RouterNode
from app.workflow.nodes._helpers import finish, require_deps

_REUSE_STATUSES = {TicketStatus.OPEN, TicketStatus.AWAITING_HUMAN}


class _ThreadContinuationRoute(RouterNode):
    def determine_next_node(self, context: ProcessingContext) -> Node | None:
        if context.is_thread_continuation:
            from app.workflow.nodes.resolution import ResolutionNode  # noqa: PLC0415

            return ResolutionNode()
        from app.workflow.nodes.triage import TriageNode  # noqa: PLC0415

        return TriageNode()


class ThreadResolutionNode(BaseRouter):
    routes = [_ThreadContinuationRoute()]
    fallback = None

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        self.context = context
        deps = require_deps(context)
        ticket = context.ticket
        if ticket is None:
            return finish(context, NodeResult(action=AuditAction.THREAD, stop_pipeline=True))

        others = [item for item in deps.tickets.list_by_thread_id(ticket.thread_id) if item.id != ticket.id]
        existing = max(others, key=lambda item: item.updated_at) if others else None
        if existing is None:
            context.is_thread_continuation = False
            result = NodeResult(action=AuditAction.THREAD, metadata={"outcome": "new_thread"})
            self.save_output(result)
            return finish(context, result)

        if existing.status in _REUSE_STATUSES:
            existing.message_id = ticket.message_id
            existing.body = ticket.body
            existing.updated_at = datetime.now(UTC)
            existing.is_thread_continuation = True
            context.ticket = existing
            context.is_thread_continuation = True
            if existing.intent is not None:
                context.ticket.intent = existing.intent
            deps.tickets.save_ticket(existing)
            result = NodeResult(
                action=AuditAction.THREAD,
                metadata={"outcome": "continuation_reuse", "skip_to_resolution": True},
            )
            self.save_output(result)
            return finish(context, result)

        if existing.status is TicketStatus.RESOLVED:
            existing.status = TicketStatus.OPEN
            existing.message_id = ticket.message_id
            existing.body = ticket.body
            existing.updated_at = datetime.now(UTC)
            existing.is_thread_continuation = True
            context.ticket = existing
            context.is_thread_continuation = True
            deps.tickets.save_ticket(existing)
            result = NodeResult(action=AuditAction.THREAD, metadata={"outcome": "reopened"})
            self.save_output(result)
            return finish(context, result)

        if existing.status is TicketStatus.ESCALATED:
            existing.message_id = ticket.message_id
            existing.body = ticket.body
            existing.updated_at = datetime.now(UTC)
            context.ticket = existing
            context.is_thread_continuation = True
            deps.tickets.save_ticket(existing)
            result = NodeResult(
                action=AuditAction.THREAD,
                metadata={"outcome": "continuation_escalated_keep"},
                stop_pipeline=True,
            )
            self.save_output(result)
            return finish(context, result)

        context.is_thread_continuation = False
        result = NodeResult(action=AuditAction.THREAD, metadata={"outcome": "new_thread_unlinked"})
        self.save_output(result)
        return finish(context, result)
