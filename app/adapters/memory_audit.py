"""In-memory audit log."""

from uuid import UUID

from app.domain.models import AuditEntry
from app.ports.audit_port import AuditPort


class InMemoryAuditLog(AuditPort):
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    def append(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    def get_by_ticket_id(self, ticket_id: UUID) -> list[AuditEntry]:
        return [entry for entry in self.entries if entry.ticket_id == ticket_id]
