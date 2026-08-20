"""Day 0 test gate — synthetic fixture coverage."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
SAP_MOCK = FIXTURES / "sap_mock"
INVOICES = FIXTURES / "invoices"
EMAILS = FIXTURES / "emails"
SENDERS = FIXTURES / "senders"

SAP_REQUIRED_FIELDS = (
    "SupplierInvoice",
    "FiscalYear",
    "CompanyCode",
    "InvoiceGrossAmount",
    "SupplierInvoiceIDByInvcgParty",
)
EXPECTED_REQUIRED_FIELDS = (
    "intent",
    "ticket_status",
    "invoice_resolution",
    "draft_target",
    "to_email",
    "attach_payment_proof",
    "human_action_needed",
)
EMAIL_NAME_RE = re.compile(r"^\d{3}_.+\.json$")


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _supplier_invoices() -> list[dict]:
    payload = _load_json(SAP_MOCK / "supplier_invoices.json")
    assert isinstance(payload, dict)
    results = payload["d"]["results"]
    assert isinstance(results, list)
    return results


def _email_files() -> list[Path]:
    return sorted(EMAILS.glob("*.json"))


def test_supplier_invoices_file_exists():
    path = SAP_MOCK / "supplier_invoices.json"
    assert path.is_file()


def test_supplier_invoices_parses_as_json():
    payload = _load_json(SAP_MOCK / "supplier_invoices.json")
    assert payload is not None


def test_supplier_invoices_has_exactly_15_entries():
    assert len(_supplier_invoices()) == 15


def test_supplier_invoices_have_required_fields():
    for invoice in _supplier_invoices():
        missing = [field for field in SAP_REQUIRED_FIELDS if field not in invoice]
        assert not missing, f"{invoice.get('SupplierInvoice')}: missing {missing}"


def test_vendor_clearing_exists_and_parses():
    payload = _load_json(SAP_MOCK / "vendor_clearing.json")
    assert "vendor_account_items" in payload


def test_payment_documents_exists_and_parses():
    payload = _load_json(SAP_MOCK / "payment_documents.json")
    assert "payment_documents" in payload


def test_structured_clean_pdf_exists_and_non_empty():
    path = INVOICES / "structured_clean.pdf"
    assert path.is_file()
    assert path.stat().st_size > 0


def test_scanned_poor_quality_png_exists_and_non_empty():
    path = INVOICES / "scanned_poor_quality.png"
    assert path.is_file()
    assert path.stat().st_size > 0


def test_all_20_email_fixtures_exist():
    files = _email_files()
    assert len(files) == 20
    assert all(EMAIL_NAME_RE.match(path.name) for path in files)
    numbers = {path.name[:3] for path in files}
    assert numbers == {f"{i:03d}" for i in range(1, 21)}


def test_each_email_fixture_has_input_and_expected():
    for path in _email_files():
        payload = _load_json(path)
        assert "input" in payload, path.name
        assert "expected" in payload, path.name


def test_each_email_expected_has_required_fields():
    for path in _email_files():
        expected = _load_json(path)["expected"]
        missing = [field for field in EXPECTED_REQUIRED_FIELDS if field not in expected]
        assert not missing, f"{path.name}: missing {missing}"


def test_sender_directory_exists():
    assert (SENDERS / "directory.json").is_file()


def test_sender_directory_has_at_least_3_senders():
    payload = _load_json(SENDERS / "directory.json")
    assert len(payload["senders"]) >= 3


def test_sender_directory_has_at_least_1_routing_rule():
    payload = _load_json(SENDERS / "directory.json")
    assert len(payload["routing_rules"]) >= 1


def test_invoice_resolution_coverage():
    values = {_load_json(path)["expected"]["invoice_resolution"] for path in _email_files()}
    required = {"NOT_FOUND", "posted_paid", "in_approval", "multiple_or_partial"}
    assert required <= values, f"missing {required - values}"


def test_ticket_status_coverage():
    values = {_load_json(path)["expected"]["ticket_status"] for path in _email_files()}
    required = {"quarantined", "discarded", "delegated"}
    assert required <= values, f"missing {required - values}"


def test_email_inputs_have_core_fields():
    for path in _email_files():
        email_input = _load_json(path)["input"]
        assert {"subject", "from", "body", "attachments"} <= email_input.keys(), path.name


def test_duplicate_pdf_matches_structured_clean():
    clean = INVOICES / "structured_clean.pdf"
    duplicate = INVOICES / "duplicate.pdf"
    assert duplicate.is_file()
    assert clean.read_bytes() == duplicate.read_bytes()


def test_scanned_good_quality_png_exists_and_non_empty():
    path = INVOICES / "scanned_good_quality.png"
    assert path.is_file()
    assert path.stat().st_size > 0


def test_sap_mock_covers_blocked_approval_and_credit_memo():
    invoices = _supplier_invoices()
    assert any(item["PaymentBlockingReason"] == "A" for item in invoices)
    assert any(item["SupplierInvoiceStatus"] == "A" for item in invoices)
    assert any(item["SupplierInvoiceIsCreditMemo"] is True for item in invoices)


def test_duplicate_invoice_refs_exist():
    refs = [item["SupplierInvoiceIDByInvcgParty"] for item in _supplier_invoices()]
    assert refs.count("INV-2026-DUP-01") == 2
