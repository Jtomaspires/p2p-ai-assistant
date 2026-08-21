"""Node 4 — sender identification (Fase 3.4)."""

from app.domain.context import ProcessingContext
from app.domain.enums import AuditAction
from app.domain.results import NodeResult
from app.workflow.core.base import Node
from app.workflow.nodes._helpers import finish, require_deps, sender_domain


class SenderIdNode(Node):
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        self.context = context
        deps = require_deps(context)
        ticket = context.ticket
        if ticket is None:
            return finish(context, NodeResult(action=AuditAction.IDENTIFY, stop_pipeline=True))

        email = ticket.sender_email.lower()
        sender = deps.senders.get_by_email(email)
        if sender is not None:
            context.sender = sender
            context.confidence_components["sender"] = 0.9
            result = NodeResult(
                action=AuditAction.IDENTIFY,
                confidence=0.9,
                metadata={"match": "email", "sender_id": sender.id},
            )
            self.save_output(result)
            return finish(context, result)

        domain_matches = deps.senders.get_by_domain(sender_domain(email))
        if len(domain_matches) == 1:
            sender = domain_matches[0]
            context.sender = sender
            context.confidence_components["sender"] = 0.6
            result = NodeResult(
                action=AuditAction.IDENTIFY,
                confidence=0.6,
                metadata={"match": "domain", "sender_id": sender.id},
            )
            self.save_output(result)
            return finish(context, result)

        context.sender = None
        context.confidence_components["sender"] = 0.0
        result = NodeResult(action=AuditAction.IDENTIFY, confidence=0.0, metadata={"match": "unknown"})
        self.save_output(result)
        return finish(context, result)
