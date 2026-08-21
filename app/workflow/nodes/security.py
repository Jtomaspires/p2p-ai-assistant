"""Node 0 — sender security (Fase 3.0)."""

from app.domain.context import ProcessingContext
from app.domain.enums import AuditAction, TicketStatus
from app.domain.results import NodeResult
from app.workflow.core.base import Node
from app.workflow.nodes._helpers import finish, require_deps, sender_domain


class SecurityNode(Node):
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        self.context = context
        deps = require_deps(context)
        event = context.event
        if event is None or context.ticket is None:
            return finish(
                context,
                NodeResult(action=AuditAction.INGEST, metadata={"reason": "missing_ticket"}, stop_pipeline=True),
            )

        domain = sender_domain(event.from_email)
        whitelist = {
            item.strip().lower()
            for item in deps.settings.SENDER_DOMAIN_WHITELIST.split(",")
            if item.strip()
        }

        if not deps.settings.SECURITY_CHECK_ENABLED:
            deps.tickets.save_ticket(context.ticket)
            result = NodeResult(action=AuditAction.PASS, confidence=1.0, metadata={"reason": "security_disabled"})
            self.save_output(result)
            return finish(context, result)

        if deps.settings.SPF_DKIM_ENABLED:
            spf = event.spf_pass
            dkim = event.dkim_pass
            if spf is False and dkim is False:
                context.ticket.status = TicketStatus.QUARANTINED
                deps.tickets.save_ticket(context.ticket)
                result = NodeResult(
                    action=AuditAction.QUARANTINE,
                    confidence=0.95,
                    metadata={"domain": domain, "spf": spf, "dkim": dkim},
                    stop_pipeline=True,
                )
                self.save_output(result)
                return finish(context, result)
            if spf is False or dkim is False:
                context.confidence_components["sender_penalty"] = -0.2
                result = NodeResult(
                    action=AuditAction.PASS,
                    confidence=0.7,
                    metadata={"domain": domain, "partial_spf_dkim": True, "penalty": -0.2},
                )
                self.save_output(result)
                deps.tickets.save_ticket(context.ticket)
                return finish(context, result)

        if domain not in whitelist:
            context.ticket.status = TicketStatus.QUARANTINED
            deps.tickets.save_ticket(context.ticket)
            result = NodeResult(
                action=AuditAction.QUARANTINE,
                confidence=0.9,
                metadata={"domain": domain, "whitelist": False},
                stop_pipeline=True,
            )
            self.save_output(result)
            return finish(context, result)

        deps.tickets.save_ticket(context.ticket)
        result = NodeResult(action=AuditAction.PASS, confidence=0.9, metadata={"domain": domain, "whitelist": True})
        self.save_output(result)
        return finish(context, result)
