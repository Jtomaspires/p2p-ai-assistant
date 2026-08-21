"""Day 2 Test Gate 1 — reference normalization and ResolutionNode."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.adapters.memory_audit import InMemoryAuditLog
from app.adapters.memory_ticket_store import InMemoryTicketStore
from app.adapters.mock_email import MockEmailAdapter
from app.adapters.mock_llm import MockLLMAdapter
from app.adapters.mock_sap import MockSAPAdapter
from app.adapters.mock_senders import MockSenderDirectory
from app.domain.context import ProcessingContext
from app.domain.deps import WorkflowDeps
from app.domain.enums import InvoiceMatchResult, InvoiceStage, InvoiceStatus, SenderType
from app.domain.models import Invoice, Sender, Ticket
from app.ports.sap_port import SAPPort
from app.workflow.nodes.resolution import ResolutionNode
from app.workflow.utils.normalise import normalize_reference
from settings import Settings


class FakeSAP(SAPPort):
    def __init__(
        self,
        approval: list[Invoice] | None = None,
        posted: list[Invoice] | None = None,
        clearing: dict | None = None,
        payment: dict | None = None,
    ) -> None:
        self.approval = approval or []
        self.posted = posted or []
        self.clearing = clearing
        self.payment = payment
        self.clearing_calls: list[tuple[str, str]] = []

    def get_approval_invoices(self) -> list[Invoice]:
        return self.approval

    def get_posted_invoices(self) -> list[Invoice]:
        return self.posted

    def get_clearing(self, vendor_id: str, document_number: str) -> dict | None:
        self.clearing_calls.append((vendor_id, document_number))
        return self.clearing

    def get_payment_document(self, clearing_document: str) -> dict | None:
        return self.payment


def _invoice(**overrides) -> Invoice:
    payload = {
        "invoice_ref": "INV-2026-0042",
        "supplier_name": "ACME Supplies Lda",
        "amount": Decimal("123.00"),
        "stage": InvoiceStage.POSTED,
        "status": InvoiceStatus.PENDING_PAYMENT,
        "sap_id": "5105600042/2026",
        "due_date": date.today() + timedelta(days=30),
    }
    payload.update(overrides)
    return Invoice.model_validate(payload)


def _deps(
    sap: SAPPort,
    llm_responses: list[dict] | None = None,
    **setting_overrides,
) -> WorkflowDeps:
    settings = Settings(
        _env_file=None,
        LLM_RETRY_BACKOFF_S=0,
        **setting_overrides,
    )
    return WorkflowDeps(
        settings=settings,
        llm=MockLLMAdapter(llm_responses or []),
        email=MockEmailAdapter(),
        tickets=InMemoryTicketStore(),
        sap=sap,
        audit=InMemoryAuditLog(),
        senders=MockSenderDirectory(),
    )


def _context(
    sap: SAPPort,
    *,
    reference: str | None = "INV-2026-0042",
    amount: Decimal | None = None,
    llm_responses: list[dict] | None = None,
) -> ProcessingContext:
    ticket = Ticket(
        thread_id="thread-resolution",
        message_id="msg-resolution",
        sender_email="billing@acme-supplies.com",
        subject="Invoice status",
        body="Please share an update.",
        received_at=datetime(2026, 8, 21, tzinfo=UTC),
    )
    sender = Sender(
        id="sender-acme",
        email=ticket.sender_email,
        name="Maria Costa",
        company="ACME Supplies Lda",
        vendor_sap_id="10300006",
        sender_type=SenderType.EXTERNAL_SUPPLIER,
    )
    deps = _deps(sap, llm_responses)
    return ProcessingContext(
        ticket=ticket,
        sender=sender,
        extracted_ref=reference,
        extracted_amount=amount,
        deps=deps,
    )


async def _run(context: ProcessingContext) -> ProcessingContext:
    return await ResolutionNode(context=context).process(context)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SCB/1234-345", "SCB1234345"),
        ("*1234345*", "1234345"),
        (None, ""),
    ],
)
def test_normalize_reference(raw, expected):
    assert normalize_reference(raw) == expected


@pytest.mark.asyncio
async def test_exact_reference_match():
    context = await _run(_context(FakeSAP(posted=[_invoice()])))
    assert context.invoice.invoice_ref == "INV-2026-0042"
    assert context.invoice_match_result is InvoiceMatchResult.UNIQUE
    assert context.last_result.metadata["match_method"] == "exact_reference"


@pytest.mark.asyncio
async def test_fuzzy_reference_match_with_one_character_missing():
    context = await _run(
        _context(FakeSAP(posted=[_invoice()]), reference="IN-2026-0042")
    )
    assert context.invoice is not None
    assert context.last_result.metadata["match_method"] == "fuzzy_reference"


@pytest.mark.asyncio
async def test_value_and_supplier_match_without_reference():
    context = await _run(
        _context(
            FakeSAP(posted=[_invoice(amount=Decimal("100.00"))]),
            reference=None,
            amount=Decimal("100.00"),
        )
    )
    assert context.invoice_match_result is InvoiceMatchResult.UNIQUE
    assert context.last_result.metadata["match_method"] == "value_supplier"


@pytest.mark.asyncio
async def test_amount_tolerance_boundary_matches():
    context = await _run(
        _context(
            FakeSAP(posted=[_invoice(amount=Decimal("100.00"))]),
            reference=None,
            amount=Decimal("102.00"),
            llm_responses=[{"operator_notes": "Amount requires review."}],
        )
    )
    assert context.invoice_match_result is InvoiceMatchResult.VAT_DISCREPANCY
    assert context.invoice is not None


@pytest.mark.asyncio
async def test_amount_just_over_tolerance_does_not_match():
    context = await _run(
        _context(
            FakeSAP(posted=[_invoice(amount=Decimal("100.00"))]),
            reference=None,
            amount=Decimal("102.01"),
        )
    )
    assert context.invoice_match_result is InvoiceMatchResult.NOT_FOUND


@pytest.mark.asyncio
async def test_vat_net_to_gross_passes_without_llm():
    context = await _run(
        _context(
            FakeSAP(posted=[_invoice(amount=Decimal("123.00"))]),
            amount=Decimal("100.00"),
        )
    )
    assert context.invoice_match_result is InvoiceMatchResult.UNIQUE
    assert context.operator_notes is None


@pytest.mark.asyncio
async def test_vat_discrepancy_calls_llm_and_records_notes():
    context = await _run(
        _context(
            FakeSAP(posted=[_invoice(amount=Decimal("123.00"))]),
            amount=Decimal("90.00"),
            llm_responses=[{"operator_notes": "Extracted net does not reconcile to gross."}],
        )
    )
    assert context.invoice_match_result is InvoiceMatchResult.VAT_DISCREPANCY
    assert context.requires_hitl is True
    assert "does not reconcile" in context.operator_notes
    assert len(context.deps.llm.calls) == 1


@pytest.mark.asyncio
async def test_not_found():
    context = await _run(
        _context(FakeSAP(posted=[_invoice()]), reference="UNKNOWN", amount=None)
    )
    assert context.invoice is None
    assert context.invoice_match_result is InvoiceMatchResult.NOT_FOUND


@pytest.mark.asyncio
async def test_duplicate_exact_reference_is_ambiguous():
    duplicate = _invoice(stage=InvoiceStage.IN_APPROVAL, status=None)
    context = await _run(
        _context(FakeSAP(approval=[duplicate], posted=[_invoice()]))
    )
    assert context.invoice is None
    assert context.invoice_match_result is InvoiceMatchResult.MULTIPLE_OR_PARTIAL
    assert context.requires_hitl is True


@pytest.mark.asyncio
async def test_more_than_five_value_candidates_is_too_many():
    invoices = [
        _invoice(invoice_ref=f"OTHER-{index}", sap_id=f"{index}/2026")
        for index in range(6)
    ]
    context = await _run(
        _context(FakeSAP(posted=invoices), reference=None, amount=Decimal("123.00"))
    )
    assert context.invoice_match_result is InvoiceMatchResult.TOO_MANY


@pytest.mark.asyncio
async def test_paid_invoice_with_clearing_populates_payment():
    context = await _run(
        _context(MockSAPAdapter(), reference="INV-2026-0005", amount=Decimal("14760.00"))
    )
    assert context.invoice.status is InvoiceStatus.PAID
    assert context.invoice.clearing_document == "1400000123"
    assert context.invoice.payment_proof_ref == "PROOF-2026-0123.pdf"
    assert context.requires_hitl is False


@pytest.mark.asyncio
async def test_paid_invoice_without_clearing_requires_hitl():
    sap = FakeSAP(
        posted=[_invoice(status=InvoiceStatus.PAID)],
        clearing=None,
    )
    context = await _run(_context(sap))
    assert sap.clearing_calls == [("10300006", "5105600042")]
    assert context.invoice.clearing_document is None
    assert context.requires_hitl is True


@pytest.mark.asyncio
async def test_no_due_date_is_not_overdue_or_near_due():
    context = await _run(
        _context(FakeSAP(posted=[_invoice(due_date=None)]))
    )
    assert context.is_overdue is False
    assert context.is_near_due is False


@pytest.mark.asyncio
async def test_due_date_flags_overdue_and_near_due():
    overdue = await _run(
        _context(FakeSAP(posted=[_invoice(due_date=date.today() - timedelta(days=1))]))
    )
    near = await _run(
        _context(FakeSAP(posted=[_invoice(due_date=date.today() + timedelta(days=3))]))
    )
    assert overdue.is_overdue is True
    assert near.is_near_due is True
