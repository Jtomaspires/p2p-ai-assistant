"""Generate synthetic Day 0 fixtures (SAP mock, invoice PDFs, emails, senders)."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
SAP_MOCK = FIXTURES / "sap_mock"
INVOICES = FIXTURES / "invoices"
EMAILS = FIXTURES / "emails"
SENDERS = FIXTURES / "senders"

VENDOR_ID = "10300006"
COMPANY_CODE = "1010"
FISCAL_YEAR = "2026"
CURRENCY = "EUR"
ACME_EMAIL = "billing@acme-supplies.com"
JOAO_EMAIL = "joao.silva@group-subsidiary.com"
ANA_EMAIL = "ana.santos@p2p-branch.com"
INVOICING_EMAIL = "invoicing@company.com"
PAYMENTS_EMAIL = "payments@company.com"
APPROVER_EMAIL = "approver@company.com"


def odata_date(year: int, month: int, day: int) -> str:
    dt = datetime(year, month, day, tzinfo=timezone.utc)
    return f"/Date({int(dt.timestamp() * 1000)})/"


def _po_item(*, net_amount: str, text: str, purchase_order: str, qty: str = "1") -> dict:
    return {
        "SupplierInvoiceItem": "1",
        "PurchaseOrder": purchase_order,
        "PurchaseOrderItem": "10",
        "Plant": COMPANY_CODE,
        "TaxCode": "V1",
        "DocumentCurrency": CURRENCY,
        "SupplierInvoiceItemAmount": net_amount,
        "PurchaseOrderQuantityUnit": "PC",
        "QuantityInPurchaseOrderUnit": qty,
        "PurchaseOrderPriceUnit": "PC",
        "QtyInPurchaseOrderPriceUnit": qty,
        "SupplierInvoiceItemText": text,
    }


def _tax_item(*, tax_amount: str, base_amount: str) -> dict:
    return {
        "TaxCode": "V1",
        "DocumentCurrency": CURRENCY,
        "TaxAmount": tax_amount,
        "TaxBaseAmountInTransCrcy": base_amount,
    }


def _invoice(
    *,
    doc: str,
    ref: str,
    document_date: str,
    posting_date: str,
    due_base: str,
    net_days: str,
    gross: str,
    tax: str,
    net: str,
    status: str,
    payment_block: str = "",
    credit_memo: bool = False,
    item_text: str = "Material ABC",
    purchase_order: str = "4500001646",
    qty: str = "1",
) -> dict:
    return {
        "SupplierInvoice": doc,
        "FiscalYear": FISCAL_YEAR,
        "CompanyCode": COMPANY_CODE,
        "DocumentDate": document_date,
        "PostingDate": posting_date,
        "SupplierInvoiceIDByInvcgParty": ref,
        "InvoicingParty": VENDOR_ID,
        "DocumentCurrency": CURRENCY,
        "InvoiceGrossAmount": gross,
        "TaxAmount": tax,
        "SupplierInvoiceStatus": status,
        "PaymentTerms": f"NT{net_days}",
        "DueCalculationBaseDate": due_base,
        "NetPaymentDays": net_days,
        "PaymentBlockingReason": payment_block,
        "AccountingDocumentType": "KG" if credit_memo else "RE",
        "SupplierInvoiceIsCreditMemo": credit_memo,
        "TaxIsCalculatedAutomatically": True,
        "to_SuplrInvcItemPurOrdRef": {
            "results": [
                _po_item(
                    net_amount=net,
                    text=item_text,
                    purchase_order=purchase_order,
                    qty=qty,
                ),
            ]
        },
        "to_SupplierInvoiceTax": {
            "results": [_tax_item(tax_amount=tax, base_amount=net)],
        },
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def generate_sap_mock() -> dict[str, int]:
    """Bloco 1 — 15 A_SupplierInvoice records + clearing + payment docs."""
    SAP_MOCK.mkdir(parents=True, exist_ok=True)

    on_time = odata_date(2026, 8, 5)
    overdue = odata_date(2026, 6, 1)
    approval_on_time = odata_date(2026, 8, 10)
    approval_overdue = odata_date(2026, 5, 15)
    paid = odata_date(2026, 6, 15)

    invoices = [
        # 1–2 POSTED pending on-time
        _invoice(
            doc="5105600001",
            ref="INV-2026-0001",
            document_date=on_time,
            posting_date=on_time,
            due_base=on_time,
            net_days="30",
            gross="12300.00",
            tax="2300.00",
            net="10000.00",
            status="",
            purchase_order="4500001646",
            qty="100",
        ),
        _invoice(
            doc="5105600002",
            ref="INV-2026-0002",
            document_date=on_time,
            posting_date=on_time,
            due_base=on_time,
            net_days="30",
            gross="4920.00",
            tax="920.00",
            net="4000.00",
            status="",
            item_text="Material DEF",
            purchase_order="4500001647",
        ),
        # 3 POSTED pending overdue
        _invoice(
            doc="5105600003",
            ref="INV-2026-0003",
            document_date=overdue,
            posting_date=overdue,
            due_base=overdue,
            net_days="30",
            gross="8610.00",
            tax="1610.00",
            net="7000.00",
            status="",
            item_text="Material GHI",
            purchase_order="4500001648",
        ),
        # 4 POSTED blocked
        _invoice(
            doc="5105600004",
            ref="INV-2026-0004",
            document_date=on_time,
            posting_date=on_time,
            due_base=on_time,
            net_days="30",
            gross="2460.00",
            tax="460.00",
            net="2000.00",
            status="",
            payment_block="A",
            item_text="Material JKL",
            purchase_order="4500001649",
        ),
        # 5–6 POSTED PAID with clearing
        _invoice(
            doc="5105600005",
            ref="INV-2026-0005",
            document_date=paid,
            posting_date=paid,
            due_base=paid,
            net_days="30",
            gross="14760.00",
            tax="2760.00",
            net="12000.00",
            status="",
            item_text="Material MNO",
            purchase_order="4500001650",
        ),
        _invoice(
            doc="5105600006",
            ref="INV-2026-0006",
            document_date=paid,
            posting_date=paid,
            due_base=paid,
            net_days="30",
            gross="3690.00",
            tax="690.00",
            net="3000.00",
            status="",
            item_text="Material PQR",
            purchase_order="4500001651",
        ),
        # 7 POSTED PAID without clearing
        _invoice(
            doc="5105600007",
            ref="INV-2026-0007",
            document_date=paid,
            posting_date=paid,
            due_base=paid,
            net_days="30",
            gross="7380.00",
            tax="1380.00",
            net="6000.00",
            status="",
            item_text="Material STU",
            purchase_order="4500001652",
        ),
        # 8–9 IN_APPROVAL on-time (SupplierInvoiceStatus="A")
        _invoice(
            doc="5105600008",
            ref="INV-2026-0008",
            document_date=approval_on_time,
            posting_date=approval_on_time,
            due_base=approval_on_time,
            net_days="30",
            gross="6150.00",
            tax="1150.00",
            net="5000.00",
            status="A",
            item_text="Material VWX",
            purchase_order="4500001653",
        ),
        _invoice(
            doc="5105600009",
            ref="INV-2026-0009",
            document_date=approval_on_time,
            posting_date=approval_on_time,
            due_base=approval_on_time,
            net_days="30",
            gross="11070.00",
            tax="2070.00",
            net="9000.00",
            status="A",
            item_text="Material YZ",
            purchase_order="4500001654",
        ),
        # 10 IN_APPROVAL overdue
        _invoice(
            doc="5105600010",
            ref="INV-2026-0010",
            document_date=approval_overdue,
            posting_date=approval_overdue,
            due_base=approval_overdue,
            net_days="30",
            gross="6765.00",
            tax="1265.00",
            net="5500.00",
            status="A",
            item_text="Material AAA",
            purchase_order="4500001655",
        ),
        # 11–12 fuzzy-match-only (different ref, value within ±2%)
        _invoice(
            doc="5105600011",
            ref="INV-ACME-7788",
            document_date=on_time,
            posting_date=on_time,
            due_base=on_time,
            net_days="30",
            gross="12546.00",
            tax="2346.00",
            net="10200.00",
            status="",
            item_text="Material ABC",
            purchase_order="4500001656",
        ),
        _invoice(
            doc="5105600012",
            ref="INV-ACME-9901",
            document_date=on_time,
            posting_date=on_time,
            due_base=on_time,
            net_days="30",
            gross="5018.40",
            tax="938.40",
            net="4080.00",
            status="",
            item_text="Material DEF",
            purchase_order="4500001657",
        ),
        # 13–14 duplicates (same ref)
        _invoice(
            doc="5105600013",
            ref="INV-2026-DUP-01",
            document_date=on_time,
            posting_date=on_time,
            due_base=on_time,
            net_days="30",
            gross="9840.00",
            tax="1840.00",
            net="8000.00",
            status="",
            item_text="Material BBB",
            purchase_order="4500001658",
        ),
        _invoice(
            doc="5105600014",
            ref="INV-2026-DUP-01",
            document_date=on_time,
            posting_date=on_time,
            due_base=on_time,
            net_days="30",
            gross="9840.00",
            tax="1840.00",
            net="8000.00",
            status="",
            item_text="Material BBB",
            purchase_order="4500001658",
        ),
        # 15 credit memo stub
        _invoice(
            doc="5105600015",
            ref="CM-2026-0001",
            document_date=on_time,
            posting_date=on_time,
            due_base=on_time,
            net_days="30",
            gross="615.00",
            tax="115.00",
            net="500.00",
            status="",
            credit_memo=True,
            item_text="Credit memo — returned goods",
            purchase_order="4500001659",
        ),
    ]

    _write_json(SAP_MOCK / "supplier_invoices.json", {"d": {"results": invoices}})

    clearing = {
        "vendor_account_items": [
            {
                "vendor": VENDOR_ID,
                "document_number": "5105600005",
                "fiscal_year": FISCAL_YEAR,
                "clearing_document": "1400000123",
                "clearing_date": "2026-07-15",
                "amount": "-14760.00",
                "currency": CURRENCY,
            },
            {
                "vendor": VENDOR_ID,
                "document_number": "5105600006",
                "fiscal_year": FISCAL_YEAR,
                "clearing_document": "1400000124",
                "clearing_date": "2026-07-20",
                "amount": "-3690.00",
                "currency": CURRENCY,
            },
        ]
    }
    _write_json(SAP_MOCK / "vendor_clearing.json", clearing)

    payments = {
        "payment_documents": [
            {
                "payment_document": "1400000123",
                "fiscal_year": FISCAL_YEAR,
                "payment_date": "2026-07-15",
                "payment_method": "T",
                "house_bank": "DB01",
                "amount": "14760.00",
                "currency": CURRENCY,
                "payment_proof_ref": "PROOF-2026-0123.pdf",
            },
            {
                "payment_document": "1400000124",
                "fiscal_year": FISCAL_YEAR,
                "payment_date": "2026-07-20",
                "payment_method": "T",
                "house_bank": "DB01",
                "amount": "3690.00",
                "currency": CURRENCY,
                "payment_proof_ref": "PROOF-2026-0124.pdf",
            },
        ]
    }
    _write_json(SAP_MOCK / "payment_documents.json", payments)

    return {
        "supplier_invoices": len(invoices),
        "vendor_clearing": len(clearing["vendor_account_items"]),
        "payment_documents": len(payments["payment_documents"]),
    }


def _draw_invoice_pdf(path: Path, *, nif: str, show_amount: bool) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    width, height = A4

    c.setTitle("INV-2026-0001")
    c.setAuthor("ACME SUPPLIES LDA")

    y = height - 25 * mm
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, y, "ACME SUPPLIES LDA")
    c.setFont("Helvetica", 9)
    c.drawRightString(width - 20 * mm, y, "INVOICE")

    y -= 7 * mm
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, y, "Rua das Industrias 100, 1000-001 Lisboa")
    y -= 5 * mm
    c.drawString(20 * mm, y, f"NIF: {nif}")
    y -= 5 * mm
    c.drawString(20 * mm, y, "Email: billing@acme-supplies.com")

    y -= 12 * mm
    c.setStrokeColorRGB(0.15, 0.15, 0.15)
    c.line(20 * mm, y, width - 20 * mm, y)

    y -= 10 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Bill to")
    c.drawString(110 * mm, y, "Invoice details")

    y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, y, "P2P Demo Company S.A.")
    c.drawString(110 * mm, y, "Invoice no.: INV-2026-0001")
    y -= 5 * mm
    c.drawString(20 * mm, y, "Company code: 1010")
    c.drawString(110 * mm, y, "Date: 05/08/2026")
    y -= 5 * mm
    c.drawString(20 * mm, y, "Vendor: 10300006")
    c.drawString(110 * mm, y, "Payment terms: NT30")
    y -= 5 * mm
    c.drawString(110 * mm, y, "Currency: EUR")

    y -= 14 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "Description")
    c.drawString(110 * mm, y, "Qty")
    c.drawRightString(width - 20 * mm, y, "Amount (EUR)")
    y -= 3 * mm
    c.line(20 * mm, y, width - 20 * mm, y)

    y -= 8 * mm
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, y, "Material ABC")
    c.drawString(110 * mm, y, "100 PC")
    if show_amount:
        c.drawRightString(width - 20 * mm, y, "10,000.00")
    else:
        c.drawRightString(width - 20 * mm, y, "")

    y -= 16 * mm
    c.line(110 * mm, y + 8 * mm, width - 20 * mm, y + 8 * mm)
    c.drawString(110 * mm, y, "Net")
    if show_amount:
        c.drawRightString(width - 20 * mm, y, "10,000.00")
    y -= 6 * mm
    c.drawString(110 * mm, y, "VAT 23% (V1)")
    if show_amount:
        c.drawRightString(width - 20 * mm, y, "2,300.00")
    y -= 8 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(110 * mm, y, "Total")
    if show_amount:
        c.drawRightString(width - 20 * mm, y, "12,300.00")
    else:
        # Amount field present but left blank (validation fixture).
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(0.55, 0.55, 0.55)
        c.drawRightString(width - 20 * mm, y, "")
        c.setFillColorRGB(0, 0, 0)

    y = 30 * mm
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, y, "Reference: INV-2026-0001  |  PO: 4500001646")
    y -= 4 * mm
    c.drawString(20 * mm, y, "This is a synthetic fixture invoice for P2P AI Assistant tests.")

    c.showPage()
    c.save()


def _find_poppler_path() -> str | None:
    if shutil.which("pdftoppm"):
        return None
    env = os.environ.get("POPPLER_PATH")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            ROOT / ".tools" / "poppler" / "Library" / "bin",
            ROOT / ".tools" / "poppler" / "bin",
        ]
    )
    for extra in ROOT.joinpath(".tools").glob("poppler-*/Library/bin"):
        candidates.append(extra)
    for candidate in candidates:
        if (candidate / "pdftoppm.exe").exists() or (candidate / "pdftoppm").exists():
            return str(candidate)
    return None


def _pdf_to_image(clean_pdf: Path):
    """Rasterise structured_clean.pdf (pdf2image/poppler, then pypdfium2, then PIL)."""
    from PIL import Image, ImageDraw, ImageFont

    poppler_path = _find_poppler_path()
    convert_kwargs = {"dpi": 150}
    if poppler_path:
        convert_kwargs["poppler_path"] = poppler_path

    try:
        from pdf2image import convert_from_path

        pages = convert_from_path(str(clean_pdf), **convert_kwargs)
        if pages:
            return pages[0]
    except Exception as exc:  # noqa: BLE001 — poppler often missing on Windows
        print(f"  warning: pdf2image failed ({exc}); trying pypdfium2")

    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(clean_pdf))
        page = pdf[0]
        bitmap = page.render(scale=150 / 72)
        return bitmap.to_pil()
    except Exception as exc:  # noqa: BLE001
        print(f"  warning: pypdfium2 failed ({exc}); using PIL stand-in")

    # Last resort from PLAN_DAY0 known risks when no PDF rasteriser is available.
    image = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    lines = [
        "ACME SUPPLIES LDA",
        "NIF: PT123456789",
        "Invoice no.: INV-2026-0001",
        "Date: 05/08/2026",
        "Material ABC    100 PC    10,000.00",
        "Net 10,000.00   VAT 23% 2,300.00",
        "Total 12,300.00 EUR",
        "[PIL fallback — poppler/pdftoppm not on PATH]",
    ]
    y = 80
    for line in lines:
        draw.text((80, y), line, fill=(20, 20, 20), font=font)
        y += 36
    return image


def generate_invoice_pdfs() -> dict[str, int]:
    """Bloco 2 — structured PDF, error PDF, duplicate, and scanned PNG variants."""
    from PIL import ImageEnhance, ImageFilter

    INVOICES.mkdir(parents=True, exist_ok=True)

    clean_pdf = INVOICES / "structured_clean.pdf"
    errors_pdf = INVOICES / "with_errors.pdf"
    duplicate_pdf = INVOICES / "duplicate.pdf"

    _draw_invoice_pdf(clean_pdf, nif="PT123456789", show_amount=True)
    _draw_invoice_pdf(errors_pdf, nif="PT000000000", show_amount=False)
    shutil.copyfile(clean_pdf, duplicate_pdf)

    image = _pdf_to_image(clean_pdf)
    good_png = INVOICES / "scanned_good_quality.png"
    poor_png = INVOICES / "scanned_poor_quality.png"
    image.save(good_png, "PNG")

    poor = image.filter(ImageFilter.GaussianBlur(radius=2))
    poor = ImageEnhance.Contrast(poor).enhance(0.6)
    poor.save(poor_png, "PNG")

    return {
        "invoice_pdfs": 3,
        "invoice_pngs": 2,
    }


_EXPECTED_REQUIRED = (
    "intent",
    "ticket_status",
    "invoice_resolution",
    "draft_target",
    "to_email",
    "attach_payment_proof",
    "human_action_needed",
)


def _email(
    number: int,
    slug: str,
    scenario: str,
    tags: list[str],
    *,
    subject: str,
    from_email: str,
    body: str,
    attachments: list[str],
    intent: str,
    ticket_status: str,
    invoice_resolution: str | None,
    draft_target: str | None,
    to_email: str | None,
    attach_invoice_pdf: bool,
    attach_payment_proof: bool,
    human_action_needed: bool,
    ticket_flag: str | None = None,
) -> tuple[str, dict]:
    payload = {
        "id": f"email_{number:03d}",
        "scenario": scenario,
        "tags": tags,
        "input": {
            "subject": subject,
            "from": from_email,
            "body": body,
            "attachments": attachments,
        },
        "expected": {
            "intent": intent,
            "ticket_status": ticket_status,
            "ticket_flag": ticket_flag,
            "invoice_resolution": invoice_resolution,
            "draft_target": draft_target,
            "to_email": to_email,
            "attach_invoice_pdf": attach_invoice_pdf,
            "attach_payment_proof": attach_payment_proof,
            "human_action_needed": human_action_needed,
        },
    }
    return f"{number:03d}_{slug}.json", payload


def generate_email_fixtures() -> dict[str, int]:
    """Bloco 3 — 20 golden-dataset emails (Fase 0.3 / Fase 6)."""
    EMAILS.mkdir(parents=True, exist_ok=True)
    cases = [
        _email(
            1,
            "invoice_not_found",
            "invoice_not_found",
            ["not_found", "invoicing", "attachment"],
            subject="Invoice INV-2026-9999 - payment status?",
            from_email=ACME_EMAIL,
            body=(
                "Dear P2P team,\n\n"
                "Could you confirm if invoice INV-2026-9999 for EUR 1,000.00 has been received?\n\n"
                "Best regards,\nMaria Costa\nACME Supplies Lda"
            ),
            attachments=["INV-2026-9999.pdf"],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="NOT_FOUND",
            draft_target="invoicing",
            to_email=INVOICING_EMAIL,
            attach_invoice_pdf=True,
            attach_payment_proof=False,
            human_action_needed=True,
        ),
        _email(
            2,
            "in_approval_on_time",
            "in_approval_on_time",
            ["in_approval", "on_time", "sender"],
            subject="Invoice INV-2026-0008 - any update?",
            from_email=ACME_EMAIL,
            body=(
                "Hello,\n\nPlease share the status of invoice INV-2026-0008 "
                "(EUR 6,150.00). It should still be within terms.\n\nMaria Costa"
            ),
            attachments=["INV-2026-0008.pdf"],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="in_approval",
            draft_target="sender",
            to_email=ACME_EMAIL,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
        ),
        _email(
            3,
            "in_approval_overdue",
            "in_approval_overdue",
            ["in_approval", "overdue", "fya"],
            subject="Invoice INV-2026-0010 is overdue",
            from_email=ACME_EMAIL,
            body=(
                "Dear team,\n\nInvoice INV-2026-0010 for EUR 6,765.00 is past due. "
                "Can you chase the approver?\n\nMaria Costa"
            ),
            attachments=["INV-2026-0010.pdf"],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="in_approval",
            draft_target="approval_owners",
            to_email=APPROVER_EMAIL,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
        ),
        _email(
            4,
            "posted_pending_on_time",
            "posted_pending_on_time",
            ["posted", "pending_payment", "on_time"],
            subject="Payment status for INV-2026-0001",
            from_email=ACME_EMAIL,
            body=(
                "Hi,\n\nCould you confirm when invoice INV-2026-0001 "
                "(EUR 12,300.00) will be paid? It is still within NT30.\n\nMaria"
            ),
            attachments=["structured_clean.pdf"],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="posted_pending",
            draft_target="sender",
            to_email=ACME_EMAIL,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
        ),
        _email(
            5,
            "posted_pending_overdue",
            "posted_pending_overdue",
            ["posted", "pending_payment", "overdue", "payments"],
            subject="INV-2026-0003 overdue - please pay",
            from_email=ACME_EMAIL,
            body=(
                "Hello,\n\nInvoice INV-2026-0003 for EUR 8,610.00 is overdue. "
                "Please process payment.\n\nMaria Costa"
            ),
            attachments=["INV-2026-0003.pdf"],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="posted_pending",
            draft_target="payments",
            to_email=PAYMENTS_EMAIL,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
        ),
        _email(
            6,
            "posted_blocked",
            "posted_blocked",
            ["posted", "blocked", "payments"],
            subject="Why is INV-2026-0004 blocked?",
            from_email=ACME_EMAIL,
            body=(
                "Dear payments team,\n\nInvoice INV-2026-0004 (EUR 2,460.00) appears "
                "blocked. What is the payment blocking reason?\n\nMaria"
            ),
            attachments=["INV-2026-0004.pdf"],
            intent="delay_reason",
            ticket_status="awaiting_human",
            invoice_resolution="posted_blocked",
            draft_target="payments",
            to_email=PAYMENTS_EMAIL,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
        ),
        _email(
            7,
            "paid_with_clearing",
            "posted_paid_with_clearing",
            ["paid", "clearing", "proof"],
            subject="Has INV-2026-0005 been paid?",
            from_email=ACME_EMAIL,
            body=(
                "Hello,\n\nPlease confirm payment of invoice INV-2026-0005 "
                "for EUR 14,760.00 and send the proof if available.\n\nMaria Costa"
            ),
            attachments=[],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="posted_paid",
            draft_target="sender",
            to_email=ACME_EMAIL,
            attach_invoice_pdf=False,
            attach_payment_proof=True,
            human_action_needed=True,
        ),
        _email(
            8,
            "paid_without_clearing",
            "posted_paid_without_clearing",
            ["paid", "no_clearing", "hitl"],
            subject="Payment confirmation for INV-2026-0007",
            from_email=ACME_EMAIL,
            body=(
                "Hi,\n\nOur records show INV-2026-0007 (EUR 7,380.00) as paid. "
                "Can you confirm and send a remittance advice?\n\nMaria"
            ),
            attachments=[],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="posted_paid",
            draft_target=None,
            to_email=None,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
            ticket_flag="hitl",
        ),
        _email(
            9,
            "multiple_candidates",
            "multiple_candidates",
            ["duplicate", "hitl"],
            subject="Status of INV-2026-DUP-01",
            from_email=ACME_EMAIL,
            body=(
                "Dear team,\n\nPlease advise on invoice INV-2026-DUP-01 "
                "for EUR 9,840.00.\n\nMaria Costa"
            ),
            attachments=[],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="multiple_or_partial",
            draft_target=None,
            to_email=None,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
            ticket_flag="hitl",
        ),
        _email(
            10,
            "invoice_both_sources",
            "invoice_both_sources",
            ["both_sources", "hitl", "sap_inconsistency"],
            subject="INV-2026-0009 showing in approval and AP",
            from_email=ACME_EMAIL,
            body=(
                "Hello,\n\nInvoice INV-2026-0009 (EUR 11,070.00) seems to appear "
                "both in approval and already posted. Please check.\n\nMaria"
            ),
            attachments=["INV-2026-0009.pdf"],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="multiple_or_partial",
            draft_target=None,
            to_email=None,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
            ticket_flag="hitl",
        ),
        _email(
            11,
            "suspicious_sender",
            "suspicious_sender",
            ["spf_fail", "quarantine"],
            subject="Urgent payment for INV-2026-0001",
            from_email="billing@acme-supp1ies.com",
            body=(
                "Please pay invoice INV-2026-0001 immediately to the new bank "
                "account in the attached form."
            ),
            attachments=["bank_change.pdf"],
            intent="unknown",
            ticket_status="quarantined",
            invoice_resolution=None,
            draft_target=None,
            to_email=None,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
            ticket_flag="suspicious_sender",
        ),
        _email(
            12,
            "not_ap_email",
            "not_ap_email",
            ["not_ap", "discard"],
            subject="Office lunch next Friday",
            from_email="newsletter@catering-example.com",
            body="Join us for lunch next Friday in the canteen. RSVP by Wednesday.",
            attachments=[],
            intent="unknown",
            ticket_status="discarded",
            invoice_resolution=None,
            draft_target=None,
            to_email=None,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=False,
        ),
        _email(
            13,
            "delegated_sender",
            "delegated_sender",
            ["delegated", "routing_rule"],
            subject="Group invoice INV-2026-0002 status",
            from_email=JOAO_EMAIL,
            body=(
                "Hi P2P,\n\nCan you check invoice INV-2026-0002 for EUR 4,920.00 "
                "on behalf of Group Subsidiary SA?\n\nJoão Silva"
            ),
            attachments=[],
            intent="payment_status",
            ticket_status="delegated",
            invoice_resolution=None,
            draft_target=None,
            to_email=None,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
            ticket_flag="delegated",
        ),
        _email(
            14,
            "thread_continuation",
            "thread_continuation",
            ["thread", "open_ticket"],
            subject="Re: Payment status for INV-2026-0001",
            from_email=ACME_EMAIL,
            body=(
                "Following up on my previous email about INV-2026-0001 "
                "(EUR 12,300.00). Any news?\n\nMaria Costa"
            ),
            attachments=[],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="posted_pending",
            draft_target="sender",
            to_email=ACME_EMAIL,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
        ),
        _email(
            15,
            "thread_existing_draft",
            "thread_existing_draft",
            ["thread", "invoicing", "no_duplicate_draft"],
            subject="Re: Invoice INV-2026-9999 - payment status?",
            from_email=ACME_EMAIL,
            body=(
                "Checking in again on INV-2026-9999. We still have no confirmation "
                "that you received the invoice.\n\nMaria"
            ),
            attachments=["INV-2026-9999.pdf"],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="NOT_FOUND",
            draft_target="invoicing",
            to_email=INVOICING_EMAIL,
            attach_invoice_pdf=True,
            attach_payment_proof=False,
            human_action_needed=True,
            ticket_flag="update_existing_draft",
        ),
        _email(
            16,
            "no_reference_fuzzy",
            "no_reference_fuzzy",
            ["no_reference", "fuzzy", "amount_match"],
            subject="Payment status for last ACME delivery",
            from_email=ACME_EMAIL,
            body=(
                "Hello,\n\nWe sent an invoice for EUR 12,546.00 (no reference in this "
                "email). Could you confirm the status?\n\nMaria Costa\nACME Supplies Lda"
            ),
            attachments=[],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="posted_pending",
            draft_target="sender",
            to_email=ACME_EMAIL,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
        ),
        _email(
            17,
            "vat_discrepancy",
            "vat_discrepancy",
            ["vat", "hitl"],
            subject="Please confirm INV-2026-0001 amount",
            from_email=ACME_EMAIL,
            body=(
                "Hi,\n\nInvoice INV-2026-0001 should be net EUR 10,000.00 plus 6% VAT "
                "(EUR 600.00), total EUR 10,600.00. Can you confirm?\n\nMaria"
            ),
            attachments=["structured_clean.pdf"],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="vat_discrepancy",
            draft_target=None,
            to_email=None,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
            ticket_flag="VAT_DISCREPANCY",
        ),
        _email(
            18,
            "no_due_date",
            "no_due_date",
            ["posted", "no_due_date", "treat_on_time"],
            subject="When will INV-2026-0002 be paid?",
            from_email=ACME_EMAIL,
            body=(
                "Dear team,\n\nInvoice INV-2026-0002 for EUR 4,920.00 has no due date "
                "on our side. What is the expected payment date?\n\nMaria Costa"
            ),
            attachments=[],
            intent="future_timing",
            ticket_status="awaiting_human",
            invoice_resolution="posted_pending",
            draft_target="sender",
            to_email=ACME_EMAIL,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
        ),
        _email(
            19,
            "no_approval_owner",
            "no_approval_owner",
            ["in_approval", "overdue", "no_owner", "hitl"],
            subject="FYA missing owner for INV-2026-0010",
            from_email=ACME_EMAIL,
            body=(
                "Hello,\n\nInvoice INV-2026-0010 (EUR 6,765.00) is overdue in approval "
                "but there is no approval owner to chase.\n\nMaria"
            ),
            attachments=[],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="in_approval",
            draft_target=None,
            to_email=None,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
            ticket_flag="hitl",
        ),
        _email(
            20,
            "no_pdf_attachment",
            "no_pdf_attachment",
            ["not_found", "no_attachment", "invoicing"],
            subject="Did you receive our invoice INV-2026-8888?",
            from_email=ACME_EMAIL,
            body=(
                "Hi,\n\nPlease confirm receipt of invoice INV-2026-8888 "
                "for EUR 3,000.00. I am not attaching the PDF this time.\n\nMaria Costa"
            ),
            attachments=[],
            intent="payment_status",
            ticket_status="awaiting_human",
            invoice_resolution="NOT_FOUND",
            draft_target="invoicing",
            to_email=INVOICING_EMAIL,
            attach_invoice_pdf=False,
            attach_payment_proof=False,
            human_action_needed=True,
            ticket_flag="sem_anexo",
        ),
    ]

    missing = [
        name
        for name, payload in cases
        if not {"input", "expected"} <= payload.keys()
        or not set(_EXPECTED_REQUIRED) <= payload["expected"].keys()
    ]
    if missing:
        raise ValueError(f"email fixtures missing required keys: {missing}")

    resolutions = {payload["expected"]["invoice_resolution"] for _, payload in cases}
    statuses = {payload["expected"]["ticket_status"] for _, payload in cases}
    required_resolutions = {"NOT_FOUND", "posted_paid", "in_approval", "multiple_or_partial"}
    required_statuses = {"quarantined", "discarded", "delegated"}
    if not required_resolutions <= resolutions:
        raise ValueError(f"missing invoice_resolution coverage: {required_resolutions - resolutions}")
    if not required_statuses <= statuses:
        raise ValueError(f"missing ticket_status coverage: {required_statuses - statuses}")

    for old in EMAILS.glob("*.json"):
        old.unlink()
    for filename, payload in cases:
        _write_json(EMAILS / filename, payload)

    return {"emails": len(cases)}


def generate_sender_directory() -> dict[str, int]:
    """Bloco 4 — sender directory + routing rules."""
    SENDERS.mkdir(parents=True, exist_ok=True)
    directory = {
        "senders": [
            {
                "email": ACME_EMAIL,
                "name": "Maria Costa",
                "company": "ACME Supplies Lda",
                "vendor_sap_id": VENDOR_ID,
                "type": "external_supplier",
            },
            {
                "email": JOAO_EMAIL,
                "name": "João Silva",
                "company": "Group Subsidiary SA",
                "vendor_sap_id": None,
                "type": "internal_group",
            },
            {
                "email": ANA_EMAIL,
                "name": "Ana Santos",
                "company": "P2P Branch",
                "vendor_sap_id": None,
                "type": "p2p_contact",
            },
        ],
        "routing_rules": [
            {
                "id": "R1",
                "domain": "group-subsidiary.com",
                "operator_id": "op_ana",
            }
        ],
    }
    _write_json(SENDERS / "directory.json", directory)
    return {
        "senders": len(directory["senders"]),
        "routing_rules": len(directory["routing_rules"]),
    }


def main() -> int:
    for directory in (SAP_MOCK, INVOICES, EMAILS, SENDERS):
        directory.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    counts.update(generate_sap_mock())
    counts.update(generate_invoice_pdfs())
    counts.update(generate_email_fixtures())
    counts.update(generate_sender_directory())

    print("Fixture generation complete:")
    for key, value in counts.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
