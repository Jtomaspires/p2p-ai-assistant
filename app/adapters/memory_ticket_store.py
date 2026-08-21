"""In-memory ticket store for Day 1 tests and local runs."""

from uuid import UUID

from app.domain.models import Ticket
from app.ports.invoice_store_port import InvoiceStorePort


class InMemoryTicketStore(InvoiceStorePort):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Ticket] = {}

    def get_by_message_id(self, message_id: str) -> Ticket | None:
        for ticket in self._by_id.values():
            if ticket.message_id == message_id:
                return ticket
        return None

    def get_by_thread_id(self, thread_id: str) -> Ticket | None:
        matches = self.list_by_thread_id(thread_id)
        if not matches:
            return None
        return max(matches, key=lambda ticket: ticket.updated_at)

    def list_by_thread_id(self, thread_id: str) -> list[Ticket]:
        return [ticket for ticket in self._by_id.values() if ticket.thread_id == thread_id]

    def get_by_id(self, ticket_id: UUID) -> Ticket | None:
        return self._by_id.get(ticket_id)

    def save_ticket(self, ticket: Ticket) -> Ticket:
        self._by_id[ticket.id] = ticket
        return ticket
