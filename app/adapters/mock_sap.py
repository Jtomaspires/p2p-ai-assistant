"""SAP mock adapter loading Day 0 fixtures."""

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.domain.enums import InvoiceStage, InvoiceStatus
from app.domain.models import Invoice
from app.ports.sap_port import SAPPort

ROOT = Path(__file__).resolve().parent.parent.parent
SAP_DIR = ROOT / "fixtures" / "sap_mock"
APPROVAL_OWNERS_PATH = SAP_DIR / "approval_owners.json"


def _odata_date(value: str) -> date | None:
    if not value or not value.startswith("/Date("):
        return None
    millis = int(value[6:].split(")")[0])
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).date()


def _map_invoice(raw: dict) -> Invoice:
    status_code = raw.get("SupplierInvoiceStatus") or ""
    stage = InvoiceStage.IN_APPROVAL if status_code == "A" else InvoiceStage.POSTED
    invoice_status: InvoiceStatus | None = None
    if stage is InvoiceStage.POSTED:
        if raw.get("PaymentBlockingReason") == "A":
            invoice_status = InvoiceStatus.BLOCKED
        else:
            invoice_status = InvoiceStatus.PENDING_PAYMENT
    sap_id = f"{raw['SupplierInvoice']}/{raw['FiscalYear']}"
    due_base = _odata_date(raw.get("DueCalculationBaseDate", ""))
    net_days = int(raw.get("NetPaymentDays") or 0)
    due_date = None
    if due_base:
        due_date = date.fromordinal(due_base.toordinal() + net_days)
    return Invoice(
        invoice_ref=raw["SupplierInvoiceIDByInvcgParty"],
        supplier_name="ACME Supplies Lda",
        amount=Decimal(raw["InvoiceGrossAmount"]),
        stage=stage,
        currency=raw.get("DocumentCurrency", "EUR"),
        status=invoice_status,
        sap_id=sap_id,
        company_code=raw.get("CompanyCode"),
        payment_blocking_reason=raw.get("PaymentBlockingReason") or None,
        due_date=due_date,
    )


class MockSAPAdapter(SAPPort):
    def __init__(self, sap_dir: Path = SAP_DIR) -> None:
        invoices_payload = json.loads((sap_dir / "supplier_invoices.json").read_text(encoding="utf-8"))
        self.invoices = [_map_invoice(item) for item in invoices_payload["d"]["results"]]
        clearing_payload = json.loads((sap_dir / "vendor_clearing.json").read_text(encoding="utf-8"))
        self.clearing = clearing_payload.get("vendor_account_items", [])
        payments_payload = json.loads((sap_dir / "payment_documents.json").read_text(encoding="utf-8"))
        self.payments = payments_payload.get("payment_documents", [])

        # Enrich approval invoices with owner emails from approval_owners fixture
        owners_path = sap_dir / "approval_owners.json"
        if owners_path.exists():
            owners_data = json.loads(owners_path.read_text(encoding="utf-8"))
            owners_map = {
                entry["invoice_ref"]: entry["owner_email"]
                for entry in owners_data.get("approval_owners", [])
            }
            for invoice in self.invoices:
                if invoice.invoice_ref in owners_map:
                    invoice.approval_owner_email = owners_map[invoice.invoice_ref]
        paid_docs = {item["document_number"] for item in self.clearing}
        for invoice in self.invoices:
            sap_doc = (invoice.sap_id or "").split("/")[0]
            if sap_doc in paid_docs:
                invoice.status = InvoiceStatus.PAID
                match = next(item for item in self.clearing if item["document_number"] == sap_doc)
                invoice.clearing_document = match["clearing_document"]
                pay = next(
                    (item for item in self.payments if item["payment_document"] == match["clearing_document"]),
                    None,
                )
                if pay:
                    invoice.payment_document = pay["payment_document"]
                    invoice.payment_date = date.fromisoformat(pay["payment_date"])
                    invoice.payment_proof_ref = pay.get("payment_proof_ref")

    def get_approval_invoices(self) -> list[Invoice]:
        return [invoice for invoice in self.invoices if invoice.stage is InvoiceStage.IN_APPROVAL]

    def get_posted_invoices(self) -> list[Invoice]:
        return [invoice for invoice in self.invoices if invoice.stage is InvoiceStage.POSTED]

    def get_clearing(self, vendor_id: str, document_number: str) -> dict | None:
        return next(
            (
                item
                for item in self.clearing
                if item["vendor"] == vendor_id and item["document_number"] == document_number
            ),
            None,
        )

    def get_payment_document(self, clearing_document: str) -> dict | None:
        return next(
            (item for item in self.payments if item["payment_document"] == clearing_document),
            None,
        )
