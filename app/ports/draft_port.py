"""Abstract port for ResponseDraft persistence."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.models import ResponseDraft


class DraftPort(ABC):
    @abstractmethod
    def save_draft(self, draft: ResponseDraft) -> ResponseDraft:
        """Persist (insert or update) a ResponseDraft."""

    @abstractmethod
    def get_by_ticket_id(self, ticket_id: UUID) -> ResponseDraft | None:
        """Return the most recent draft for a given ticket, or None."""
