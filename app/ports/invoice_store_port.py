"""Ticket store port (invoice-adjacent persistence used by ingest/thread)."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.models import Ticket


class InvoiceStorePort(ABC):
    @abstractmethod
    def get_by_message_id(self, message_id: str) -> Ticket | None:
        pass

    @abstractmethod
    def get_by_thread_id(self, thread_id: str) -> Ticket | None:
        pass

    @abstractmethod
    def list_by_thread_id(self, thread_id: str) -> list[Ticket]:
        pass

    @abstractmethod
    def get_by_id(self, ticket_id: UUID) -> Ticket | None:
        pass

    @abstractmethod
    def save_ticket(self, ticket: Ticket) -> Ticket:
        pass
