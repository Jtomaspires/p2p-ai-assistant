"""Node 6 — deterministic invoice resolution with LLM reasoning only on VAT mismatch."""

from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher

from pydantic import BaseModel

from app.domain.context import ProcessingContext
from app.domain.enums import AuditAction, InvoiceMatchResult, InvoiceStage, InvoiceStatus
from app.domain.models import Invoice
from app.domain.results import NodeResult
from app.workflow.core.agent_node import AgentNode
from app.workflow.nodes._helpers import finish, require_deps
from app.workflow.utils.normalise import normalize_reference


class VATReasoningOutput(BaseModel):
    operator_notes: str


class ResolutionNode(AgentNode):
    """Resolve an extracted invoice against approval and posted SAP data."""

    fuzzy_threshold = 0.85

    def get_output_schema(self) -> type[BaseModel]:
        return VATReasoningOutput

    def build_system_prompt(self, context: ProcessingContext) -> str:
        return (
            "Explain an invoice VAT discrepancy for a P2P operator. Use only the "
            "provided amounts. Do not claim that an invoice is paid or valid."
        )

    def build_user_prompt(self, context: ProcessingContext) -> str:
        invoice = context.invoice
        if invoice is None:
            raise ValueError("ResolutionNode requires a matched invoice for VAT reasoning")
        return (
            f"Extracted amount: {context.extracted_amount}; "
            f"SAP gross amount: {invoice.amount}; "
            f"configured VAT rate: {require_deps(context).settings.VAT_RATE}."
        )

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        self.context = context
        deps = require_deps(context)
        approval = deps.sap.get_approval_invoices()
        posted = deps.sap.get_posted_invoices()
        candidates = approval + posted

        context.invoice = None
        context.invoice_match_result = None
        context.is_overdue = False
        context.is_near_due = False
        context.requires_hitl = False
        context.operator_notes = None

        invoice, match_result, match_method, confidence = self._match_invoice(
            context, candidates
        )
        context.invoice_match_result = match_result

        if invoice is None:
            context.requires_hitl = match_result is not InvoiceMatchResult.NOT_FOUND
            result = NodeResult(
                action=AuditAction.RESOLVE,
                confidence=confidence,
                metadata={
                    "match_result": match_result.value,
                    "match_method": match_method,
                    "candidate_count": len(candidates),
                    "requires_hitl": context.requires_hitl,
                },
            )
            self.save_output(result)
            return finish(context, result)

        context.invoice = invoice.model_copy(deep=True)
        if self._exists_in_both_sources(context.invoice, approval, posted):
            context.invoice_match_result = InvoiceMatchResult.MULTIPLE_OR_PARTIAL
            context.requires_hitl = True
            result = NodeResult(
                action=AuditAction.RESOLVE,
                confidence=0.3,
                metadata={
                    "match_result": InvoiceMatchResult.MULTIPLE_OR_PARTIAL.value,
                    "match_method": "both_sources",
                    "invoice_ref": context.invoice.invoice_ref,
                    "requires_hitl": True,
                },
            )
            self.save_output(result)
            return finish(context, result)

        vat_ok = self._vat_is_consistent(
            extracted_amount=context.extracted_amount,
            gross_amount=context.invoice.amount,
            vat_rate=Decimal(str(deps.settings.VAT_RATE)),
        )
        if not vat_ok:
            context.invoice_match_result = InvoiceMatchResult.VAT_DISCREPANCY
            context.requires_hitl = True
            reasoning = await self.call_llm(context)
            if not isinstance(reasoning, VATReasoningOutput):
                raise TypeError("LLMPort returned an unexpected VAT reasoning type")
            context.operator_notes = reasoning.operator_notes

        if (
            context.invoice.stage is InvoiceStage.POSTED
            and context.invoice.status is InvoiceStatus.PAID
        ):
            self._populate_clearing(context)

        self._evaluate_due_date(context)
        final_result = context.invoice_match_result or InvoiceMatchResult.UNIQUE
        context.invoice_match_result = final_result
        result = NodeResult(
            action=AuditAction.RESOLVE,
            confidence=0.4 if final_result is InvoiceMatchResult.VAT_DISCREPANCY else confidence,
            metadata={
                "match_result": final_result.value,
                "match_method": match_method,
                "invoice_ref": context.invoice.invoice_ref,
                "is_overdue": context.is_overdue,
                "is_near_due": context.is_near_due,
                "requires_hitl": context.requires_hitl,
                "operator_notes": context.operator_notes,
            },
        )
        self.save_output(result)
        return finish(context, result)

    def _match_invoice(
        self,
        context: ProcessingContext,
        candidates: list[Invoice],
    ) -> tuple[Invoice | None, InvoiceMatchResult, str, float]:
        normalized = normalize_reference(context.extracted_ref)
        if normalized:
            exact = [
                invoice
                for invoice in candidates
                if normalize_reference(invoice.invoice_ref) == normalized
            ]
            if len(exact) == 1:
                return exact[0], InvoiceMatchResult.UNIQUE, "exact_reference", 0.95
            if len(exact) > 1:
                return (
                    None,
                    InvoiceMatchResult.MULTIPLE_OR_PARTIAL,
                    "exact_reference_ambiguous",
                    0.3,
                )

            fuzzy = [
                invoice
                for invoice in candidates
                if SequenceMatcher(
                    None, normalized, normalize_reference(invoice.invoice_ref)
                ).ratio()
                >= self.fuzzy_threshold
            ]
            if len(fuzzy) == 1:
                return fuzzy[0], InvoiceMatchResult.UNIQUE, "fuzzy_reference", 0.8

        value_supplier = self._value_supplier_candidates(context, candidates)
        if len(value_supplier) == 1:
            return (
                value_supplier[0],
                InvoiceMatchResult.UNIQUE,
                "value_supplier",
                0.65,
            )
        if len(value_supplier) > 5:
            return None, InvoiceMatchResult.TOO_MANY, "value_supplier", 0.2
        if len(value_supplier) > 1:
            return (
                None,
                InvoiceMatchResult.MULTIPLE_OR_PARTIAL,
                "value_supplier",
                0.3,
            )
        return None, InvoiceMatchResult.NOT_FOUND, "none", 0.2

    @staticmethod
    def _value_supplier_candidates(
        context: ProcessingContext,
        candidates: list[Invoice],
    ) -> list[Invoice]:
        if context.extracted_amount is None or context.sender is None:
            return []
        supplier = context.sender.company.casefold()
        pct = Decimal(str(require_deps(context).settings.MATCH_VALUE_TOLERANCE_PCT))
        absolute = Decimal(str(require_deps(context).settings.MATCH_VALUE_TOLERANCE_ABS))
        matches: list[Invoice] = []
        for invoice in candidates:
            tolerance = max(invoice.amount * pct, absolute)
            amount_matches = abs(context.extracted_amount - invoice.amount) <= tolerance
            invoice_supplier = invoice.supplier_name.casefold()
            supplier_matches = (
                supplier in invoice_supplier or invoice_supplier in supplier
            )
            if amount_matches and supplier_matches:
                matches.append(invoice)
        return matches

    @staticmethod
    def _vat_is_consistent(
        *,
        extracted_amount: Decimal | None,
        gross_amount: Decimal,
        vat_rate: Decimal,
    ) -> bool:
        if extracted_amount is None:
            return True
        cent = Decimal("0.01")
        direct_gross_match = abs(extracted_amount - gross_amount) <= cent
        net_to_gross_match = (
            abs(extracted_amount * (Decimal("1") + vat_rate) - gross_amount) <= cent
        )
        return direct_gross_match or net_to_gross_match

    @staticmethod
    def _exists_in_both_sources(
        invoice: Invoice,
        approval: list[Invoice],
        posted: list[Invoice],
    ) -> bool:
        reference = normalize_reference(invoice.invoice_ref)
        return any(
            normalize_reference(item.invoice_ref) == reference for item in approval
        ) and any(normalize_reference(item.invoice_ref) == reference for item in posted)

    @staticmethod
    def _populate_clearing(context: ProcessingContext) -> None:
        deps = require_deps(context)
        invoice = context.invoice
        if invoice is None:
            return
        vendor_id = context.sender.vendor_sap_id if context.sender else None
        document_number = (invoice.sap_id or "").split("/", 1)[0]
        if not vendor_id or not document_number:
            context.requires_hitl = True
            return
        clearing = deps.sap.get_clearing(vendor_id, document_number)
        if not clearing:
            invoice.clearing_document = None
            invoice.payment_document = None
            invoice.payment_date = None
            invoice.payment_proof_ref = None
            context.requires_hitl = True
            return
        invoice.clearing_document = clearing.get("clearing_document")
        if not invoice.clearing_document:
            context.requires_hitl = True
            return
        payment = deps.sap.get_payment_document(invoice.clearing_document)
        if not payment:
            context.requires_hitl = True
            return
        invoice.payment_document = payment.get("payment_document")
        payment_date = payment.get("payment_date")
        invoice.payment_date = date.fromisoformat(payment_date) if payment_date else None
        invoice.payment_proof_ref = payment.get("payment_proof_ref")

    @staticmethod
    def _evaluate_due_date(context: ProcessingContext) -> None:
        invoice = context.invoice
        if invoice is None or invoice.due_date is None:
            return
        today = date.today()
        context.is_overdue = invoice.due_date < today
        context.is_near_due = (
            not context.is_overdue
            and invoice.due_date
            <= today + timedelta(days=require_deps(context).settings.NEAR_DUE_DAYS)
        )
