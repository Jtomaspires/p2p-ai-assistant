"""Audit trail port."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.models import AuditEntry


class AuditPort(ABC):
    @abstractmethod
    def append(self, entry: AuditEntry) -> None:
        pass

    @abstractmethod
    def get_by_ticket_id(self, ticket_id: UUID) -> list[AuditEntry]:
        pass
