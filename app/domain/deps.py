"""Runtime ports injected into ProcessingContext (not persisted)."""

from dataclasses import dataclass

from app.ports.audit_port import AuditPort
from app.ports.draft_port import DraftPort
from app.ports.email_port import EmailPort
from app.ports.invoice_store_port import InvoiceStorePort
from app.ports.llm_port import LLMPort
from app.ports.sap_port import SAPPort
from app.ports.sender_directory_port import SenderDirectoryPort
from settings import Settings


@dataclass
class WorkflowDeps:
    settings: Settings
    llm: LLMPort
    email: EmailPort
    tickets: InvoiceStorePort
    sap: SAPPort
    audit: AuditPort
    senders: SenderDirectoryPort
    drafts: DraftPort
