"""Node 2 — AP/P2P triage (Fase 3.2). RouterNode decides discard vs continue."""

from pydantic import BaseModel

from app.domain.context import ProcessingContext
from app.domain.enums import AuditAction, TicketStatus
from app.domain.results import NodeResult
from app.workflow.core.agent_node import AgentNode
from app.workflow.core.base import BaseRouter, Node, RouterNode
from app.workflow.nodes._helpers import finish, require_deps
from app.workflow.nodes.intent import IntentNode


class TriageOutput(BaseModel):
    is_ap: bool
    confidence: float


class DiscardRoute(RouterNode):
    def determine_next_node(self, context: ProcessingContext) -> Node | None:
        if context.ticket is not None and context.ticket.status is TicketStatus.DISCARDED:
            return None
        return None


class ContinueAfterTriageRoute(RouterNode):
    def determine_next_node(self, context: ProcessingContext) -> Node | None:
        if context.ticket is None or context.ticket.status is TicketStatus.DISCARDED:
            return None
        if context.is_thread_continuation:
            return None
        return IntentNode()


class TriageNode(AgentNode, BaseRouter):
    routes = [ContinueAfterTriageRoute()]
    fallback = None

    def get_output_schema(self) -> type[BaseModel]:
        return TriageOutput

    def build_system_prompt(self, context: ProcessingContext) -> str:
        return "Classify whether this email is accounts-payable / P2P. Bias toward yes."

    def build_user_prompt(self, context: ProcessingContext) -> str:
        ticket = context.ticket
        if ticket is None:
            raise ValueError("TriageNode requires a ticket")
        return f"Subject: {ticket.subject}\n\n{ticket.body}"

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        self.context = context
        deps = require_deps(context)
        ticket = context.ticket
        if ticket is None:
            return finish(context, NodeResult(action=AuditAction.CLASSIFY, stop_pipeline=True))

        if context.is_thread_continuation:
            result = NodeResult(action=AuditAction.CLASSIFY, metadata={"skipped": "thread_continuation"})
            self.save_output(result)
            return finish(context, result)

        output = await self.call_llm(context)
        if not isinstance(output, TriageOutput):
            raise TypeError("LLMPort returned an unexpected output type")
        is_ap = output.is_ap
        confidence = output.confidence
        context.confidence_components["triage"] = confidence
        self.save_output(output)

        discard_threshold = deps.settings.TRIAGE_DISCARD_MIN_CONFIDENCE
        if (not is_ap) and confidence >= discard_threshold:
            ticket.status = TicketStatus.DISCARDED
            deps.tickets.save_ticket(ticket)
            result = NodeResult(
                action=AuditAction.DISCARD,
                confidence=confidence,
                metadata={"is_ap": is_ap},
                stop_pipeline=True,
            )
            return finish(context, result)

        result = NodeResult(action=AuditAction.CLASSIFY, confidence=confidence, metadata={"is_ap": is_ap})
        return finish(context, result)
