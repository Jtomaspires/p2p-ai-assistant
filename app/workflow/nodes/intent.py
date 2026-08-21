"""Node 3 — intent classification (Fase 3.3). Router skips sender/routing when UNKNOWN."""

from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from app.domain.context import ProcessingContext
from app.domain.enums import AuditAction, Intent
from app.domain.results import NodeResult
from app.workflow.core.agent_node import AgentNode
from app.workflow.core.base import BaseRouter, Node, RouterNode
from app.workflow.nodes._helpers import finish, require_deps
from app.workflow.nodes.sender import SenderIdNode


class IntentOutput(BaseModel):
    intent: str
    confidence: float
    language: str | None = None
    extracted_ref: str | None = None
    extracted_amount: str | None = None
    extracted_date: str | None = None


class ContinueToSenderRoute(RouterNode):
    def determine_next_node(self, context: ProcessingContext) -> Node | None:
        if context.skip_identity:
            return None
        return SenderIdNode()


class IntentNode(AgentNode, BaseRouter):
    routes = [ContinueToSenderRoute()]
    fallback = None

    def get_output_schema(self) -> type[BaseModel]:
        return IntentOutput

    def build_system_prompt(self, context: ProcessingContext) -> str:
        return "Extract P2P intent and invoice fields as JSON."

    def build_user_prompt(self, context: ProcessingContext) -> str:
        ticket = context.ticket
        if ticket is None:
            raise ValueError("IntentNode requires a ticket")
        return f"Subject: {ticket.subject}\n\n{ticket.body}"

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        self.context = context
        deps = require_deps(context)
        ticket = context.ticket
        if ticket is None:
            return finish(context, NodeResult(action=AuditAction.CLASSIFY, stop_pipeline=True))

        output = await self.call_llm(context)
        if not isinstance(output, IntentOutput):
            raise TypeError("LLMPort returned an unexpected output type")
        raw_intent = output.intent.lower()
        try:
            intent = Intent(raw_intent)
        except ValueError:
            intent = Intent.UNKNOWN
        confidence = output.confidence
        language = output.language
        extracted_ref = output.extracted_ref
        extracted_amount = output.extracted_amount

        ticket.intent = intent
        ticket.language = language
        context.extracted_ref = extracted_ref
        if extracted_amount not in (None, ""):
            try:
                context.extracted_amount = Decimal(str(extracted_amount))
            except InvalidOperation:
                context.extracted_amount = None
        context.confidence_components["intent"] = confidence
        self.save_output(output)

        if intent is Intent.UNKNOWN or confidence < deps.settings.INTENT_MIN_CONFIDENCE:
            ticket.intent = Intent.UNKNOWN
            ticket.assigned_operator_id = deps.settings.DEFAULT_OPERATOR_ID
            context.skip_identity = True
            deps.tickets.save_ticket(ticket)
            result = NodeResult(
                action=AuditAction.CLASSIFY,
                confidence=confidence,
                metadata={"skip_identity": True, "intent": Intent.UNKNOWN.value},
            )
            return finish(context, result)

        deps.tickets.save_ticket(ticket)
        result = NodeResult(
            action=AuditAction.CLASSIFY,
            confidence=confidence,
            metadata={"intent": intent.value, "extracted_ref": extracted_ref},
        )
        return finish(context, result)
