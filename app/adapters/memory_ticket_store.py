"""In-memory ticket store for Day 1 tests and local runs."""

from uuid import UUID

from app.domain.enums import TicketStatus
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

    def list_tickets(
        self,
        status: str | None = None,
        assigned_operator_id: str | None = None,
    ) -> list[Ticket]:
        tickets = list(self._by_id.values())
        if status is not None:
            tickets = [ticket for ticket in tickets if ticket.status.value == status]
        if assigned_operator_id is not None:
            tickets = [
                ticket
                for ticket in tickets
                if ticket.assigned_operator_id == assigned_operator_id
            ]
        tickets.sort(key=lambda ticket: ticket.received_at, reverse=True)
        return tickets

    def count_by_status(self) -> dict[str, int]:
        counts = {member.value: 0 for member in TicketStatus}
        for ticket in self._by_id.values():
            counts[ticket.status.value] += 1
        return counts
