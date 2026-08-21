"""Draft generation prompt templates — one per DraftTarget.

Templates are kept here so DraftNode's build_system_prompt / build_user_prompt
can load them without embedding multi-line strings inside node logic.
"""

from app.domain.enums import DraftTarget

SYSTEM_PROMPTS: dict[DraftTarget, str] = {
    DraftTarget.SENDER: (
        "You are a professional P2P accounts-payable assistant. "
        "Write a concise, polite reply to a supplier who asked about an invoice payment status. "
        "Use ONLY the data provided — never invent facts, dates, or amounts. "
        "Address the supplier by email. Keep the tone formal and helpful."
    ),
    DraftTarget.INVOICING: (
        "You are a professional P2P accounts-payable assistant. "
        "Write a polite reply to a supplier whose invoice could NOT be located in our system. "
        "Instruct them to resubmit the invoice or contact the invoicing team. "
        "Use ONLY the data provided — never invent facts, dates, or amounts."
    ),
    DraftTarget.APPROVAL_OWNERS: (
        "You are a professional P2P accounts-payable assistant. "
        "Write a concise internal chaser email to an invoice approval owner asking them to approve "
        "an overdue or near-due supplier invoice. "
        "CC the supplier's original request for context. "
        "Use ONLY the data provided — never invent facts, dates, or amounts."
    ),
    DraftTarget.PAYMENTS: (
        "You are a professional P2P accounts-payable assistant. "
        "Write a concise internal notification email to the payments team about a supplier invoice "
        "that is overdue or payment-blocked and requires action. "
        "Use ONLY the data provided — never invent facts, dates, or amounts."
    ),
}

USER_PROMPT_TEMPLATE = """\
Ticket language: {language}

Supplier email: {sender_email}
Invoice reference: {invoice_ref}
Invoice amount: {invoice_amount} {currency}
Invoice status: {invoice_status}
Due date: {due_date}
Approval owner: {approval_owner}
Payment document: {payment_document}
Payment date: {payment_date}
Additional notes: {operator_notes}

Generate the email draft now.
"""


def build_user_prompt(
    *,
    language: str | None,
    sender_email: str,
    invoice_ref: str | None,
    invoice_amount: str | None,
    currency: str = "EUR",
    invoice_status: str | None,
    due_date: str | None,
    approval_owner: str | None,
    payment_document: str | None,
    payment_date: str | None,
    operator_notes: str | None,
) -> str:
    return USER_PROMPT_TEMPLATE.format(
        language=language or "en",
        sender_email=sender_email,
        invoice_ref=invoice_ref or "N/A",
        invoice_amount=invoice_amount or "N/A",
        currency=currency,
        invoice_status=invoice_status or "N/A",
        due_date=str(due_date) if due_date else "N/A",
        approval_owner=approval_owner or "N/A",
        payment_document=payment_document or "N/A",
        payment_date=str(payment_date) if payment_date else "N/A",
        operator_notes=operator_notes or "none",
    )
