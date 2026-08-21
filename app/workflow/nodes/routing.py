"""Node 5 — routing (Fase 3.5). RouterNode stops on DELEGATE."""

from app.domain.context import ProcessingContext
from app.domain.enums import AuditAction, TicketStatus
from app.domain.results import NodeResult
from app.workflow.core.base import BaseRouter, Node, RouterNode
from app.workflow.nodes._helpers import finish, require_deps, sender_domain


class ContinueAfterRoutingRoute(RouterNode):
    def determine_next_node(self, context: ProcessingContext) -> Node | None:
        if context.ticket is not None and context.ticket.status is TicketStatus.DELEGATED:
            return None
        return None


class RoutingNode(BaseRouter):
    routes = [ContinueAfterRoutingRoute()]
    fallback = None

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        self.context = context
        deps = require_deps(context)
        ticket = context.ticket
        if ticket is None:
            return finish(context, NodeResult(action=AuditAction.MINE, stop_pipeline=True))

        email = ticket.sender_email.lower()
        rule = deps.senders.get_routing_rule_by_email(email)
        if rule is None:
            rule = deps.senders.get_routing_rule_by_domain(sender_domain(email))

        default_operator = deps.settings.DEFAULT_OPERATOR_ID
        if rule is not None and rule.operator_id != default_operator:
            ticket.status = TicketStatus.DELEGATED
            ticket.assigned_operator_id = rule.operator_id
            deps.tickets.save_ticket(ticket)
            result = NodeResult(
                action=AuditAction.DELEGATE,
                confidence=1.0,
                metadata={"rule_id": rule.id, "operator_id": rule.operator_id},
                stop_pipeline=True,
            )
            self.save_output(result)
            return finish(context, result)

        ticket.assigned_operator_id = default_operator
        deps.tickets.save_ticket(ticket)
        result = NodeResult(
            action=AuditAction.MINE,
            confidence=1.0,
            metadata={"operator_id": default_operator, "rule_id": rule.id if rule else None},
        )
        self.save_output(result)
        return finish(context, result)
