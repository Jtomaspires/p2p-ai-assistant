"""Node 6.5 — response draft generation (Fase 3.6.5).

Target selection is fully deterministic (no LLM). The LLM only writes the text.
"""

from pydantic import BaseModel

from app.domain.context import ProcessingContext
from app.domain.enums import (
    AuditAction,
    DraftTarget,
    InvoiceMatchResult,
    InvoiceStage,
    InvoiceStatus,
)
from app.domain.models import ResponseDraft
from app.domain.results import NodeResult
from app.llm import prompts as _prompts
from app.workflow.core.agent_node import AgentNode
from app.workflow.nodes._helpers import finish, require_deps


class DraftOutput(BaseModel):
    generated_text: str


class DraftNode(AgentNode):
    """Generate a ResponseDraft: deterministic target, then LLM text."""

    def get_output_schema(self) -> type[BaseModel]:
        return DraftOutput

    def build_system_prompt(self, context: ProcessingContext) -> str:
        target = context.metadata.get("_draft_target")
        if isinstance(target, DraftTarget):
            return _prompts.SYSTEM_PROMPTS[target]
        return _prompts.SYSTEM_PROMPTS[DraftTarget.SENDER]

    def build_user_prompt(self, context: ProcessingContext) -> str:
        deps = require_deps(context)
        ticket = context.ticket
        invoice = context.invoice
        return _prompts.build_user_prompt(
            language=ticket.language if ticket else None,
            sender_email=ticket.sender_email if ticket else "",
            invoice_ref=invoice.invoice_ref if invoice else context.extracted_ref,
            invoice_amount=str(invoice.amount) if invoice else (
                str(context.extracted_amount) if context.extracted_amount else None
            ),
            currency=invoice.currency if invoice else "EUR",
            invoice_status=invoice.status.value if (invoice and invoice.status) else (
                invoice.stage.value if invoice else None
            ),
            due_date=invoice.due_date if invoice else None,
            approval_owner=invoice.approval_owner_email if invoice else None,
            payment_document=invoice.payment_document if invoice else None,
            payment_date=invoice.payment_date if invoice else None,
            operator_notes=context.operator_notes,
        )

    # ------------------------------------------------------------------
    # Deterministic target selection (decision table from Fase 3.6.5)
    # ------------------------------------------------------------------

    def _pick_target(
        self, context: ProcessingContext
    ) -> tuple[DraftTarget | None, str, bool]:
        """Return (target, to_email, attach_payment_proof).

        Returns (None, "", False) when the case routes to HITL with no draft.
        """
        deps = require_deps(context)
        settings = deps.settings
        ticket = context.ticket
        invoice = context.invoice
        match_result = context.invoice_match_result

        sender_email = ticket.sender_email if ticket else ""

        # --- Ambiguous / multi-match / VAT discrepancy → HITL, no draft ---
        # Must be checked BEFORE the NOT_FOUND / invoice-is-None guard
        if match_result in (
            InvoiceMatchResult.MULTIPLE_OR_PARTIAL,
            InvoiceMatchResult.TOO_MANY,
            InvoiceMatchResult.VAT_DISCREPANCY,
        ):
            return None, "", False

        if context.requires_hitl and match_result is not InvoiceMatchResult.UNIQUE:
            return None, "", False

        # --- Not found at all ---
        if match_result is InvoiceMatchResult.NOT_FOUND or invoice is None:
            return DraftTarget.INVOICING, settings.INVOICING_EMAIL, False

        # --- IN_APPROVAL ---
        if invoice.stage is InvoiceStage.IN_APPROVAL:
            if context.is_overdue or context.is_near_due:
                owner = invoice.approval_owner_email
                if owner:
                    return DraftTarget.APPROVAL_OWNERS, owner, False
                return None, "", False  # no owner → HITL
            return DraftTarget.SENDER, sender_email, False

        # --- POSTED ---
        if invoice.stage is InvoiceStage.POSTED:
            if invoice.status is InvoiceStatus.BLOCKED:
                return DraftTarget.PAYMENTS, settings.PAYMENTS_EMAIL, False
            if invoice.status is InvoiceStatus.PENDING_PAYMENT:
                if context.is_overdue:
                    return DraftTarget.PAYMENTS, settings.PAYMENTS_EMAIL, False
                return DraftTarget.SENDER, sender_email, False
            if invoice.status is InvoiceStatus.PAID:
                if invoice.clearing_document:
                    return DraftTarget.SENDER, sender_email, True
                return None, "", False  # paid but no clearing → HITL
            if invoice.status is InvoiceStatus.PARTIALLY_PAID:
                return DraftTarget.SENDER, sender_email, False

        # Fallback: any remaining requires_hitl
        if context.requires_hitl:
            return None, "", False

        return DraftTarget.SENDER, sender_email, False

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        self.context = context
        ticket = context.ticket
        if ticket is None:
            return finish(context, NodeResult(action=AuditAction.DRAFT, stop_pipeline=True))

        target, to_email, attach_payment_proof = self._pick_target(context)

        if target is None:
            # HITL path — no draft generated, flag and pass through
            context.requires_hitl = True
            result = NodeResult(
                action=AuditAction.DRAFT,
                confidence=0.0,
                metadata={"target": None, "reason": "no_draft_hitl"},
            )
            self.save_output(result)
            return finish(context, result)

        # Store target so build_system_prompt can retrieve it
        context.metadata["_draft_target"] = target

        output = await self.call_llm(context)
        if not isinstance(output, DraftOutput):
            raise TypeError("DraftNode: unexpected LLM output type")

        draft = ResponseDraft(
            ticket_id=ticket.id,
            target=target,
            to_email=to_email,
            generated_text=output.generated_text,
            attach_payment_proof=attach_payment_proof,
            attach_invoice_pdf=(target is DraftTarget.INVOICING),
            operator_notes=context.operator_notes,
        )
        context.draft = draft

        result = NodeResult(
            action=AuditAction.DRAFT,
            confidence=0.9,
            metadata={
                "target": target.value,
                "to_email": to_email,
                "attach_payment_proof": attach_payment_proof,
            },
        )
        self.save_output(result)
        return finish(context, result)
