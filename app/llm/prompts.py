"""LLM prompt templates loaded by AgentNode subclasses.

Keep prompt text here so nodes only call builders in `build_system_prompt` /
`build_user_prompt` — matching DraftNode's pattern.
"""

from app.domain.enums import DraftTarget, Intent

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


INTENT_SYSTEM_PROMPT = """\
You classify supplier emails for a Procure-to-Pay (accounts-payable) team.

Return JSON only. The `intent` field MUST be exactly one of these values:
- payment_status
- delay_reason
- future_timing
- unknown

Rules:
- Questions about payment or receipt of an invoice → payment_status.
  Examples: "Has INV-2026-0001 been paid?", "Confirm if invoice INV-2026-9999 was received".
- Questions about why a payment is late / blocked / overdue → delay_reason.
  Examples: "Why is INV-2026-0010 still unpaid?", "What is blocking payment of this invoice?".
- Questions about when a future payment will happen (timing, due date, expected date) → future_timing.
  Examples: "When will INV-2026-0008 be paid?", "What is the expected payment date?".
- Use unknown ONLY when there is genuinely no clear P2P payment signal
  (greeting-only mail, unrelated request, or mixed/unreadable content).
  Examples: "Please update our bank details", "Can you share the PO PDF?".

Also extract:
- language: ISO-like code of the email (e.g. "en", "pt") if detectable, else null
- extracted_ref: invoice reference if present (e.g. INV-2026-9999), else null
- extracted_amount: numeric amount string if present (e.g. "1000.00"), else null
- extracted_date: date string if present, else null
- confidence: a number between 0 and 1 (inclusive)
"""

TRIAGE_SYSTEM_PROMPT = """\
Classify whether this email belongs to accounts-payable / Procure-to-Pay (P2P).

Return JSON with:
- is_ap: true if the email is about invoices, payments, payment status, due dates,
  approval of supplier invoices, or related AP operations; false otherwise.
- confidence: a number between 0 and 1 (inclusive).

Bias toward yes (is_ap=true) when the email mentions an invoice reference, amount,
payment, or supplier billing. Lunch invites, newsletters, and unrelated internal
mail are not AP.
"""


def build_intent_system_prompt() -> str:
    """System prompt for IntentNode (valid Intent enum values listed explicitly)."""
    allowed = ", ".join(member.value for member in Intent)
    return f"{INTENT_SYSTEM_PROMPT}\nAllowed intent values: {allowed}."


def build_intent_user_prompt(*, subject: str, body: str) -> str:
    return f"Subject: {subject}\n\n{body}"


def build_triage_system_prompt() -> str:
    return TRIAGE_SYSTEM_PROMPT


def build_triage_user_prompt(*, subject: str, body: str) -> str:
    return f"Subject: {subject}\n\n{body}"


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
