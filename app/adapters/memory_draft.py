"""In-memory DraftPort implementation for tests and local runs."""

from uuid import UUID

from app.domain.models import ResponseDraft
from app.ports.draft_port import DraftPort


class InMemoryDraftStore(DraftPort):
    def __init__(self) -> None:
        self._store: dict[UUID, ResponseDraft] = {}

    def save_draft(self, draft: ResponseDraft) -> ResponseDraft:
        self._store[draft.id] = draft
        return draft

    def get_by_ticket_id(self, ticket_id: UUID) -> ResponseDraft | None:
        matches = [d for d in self._store.values() if d.ticket_id == ticket_id]
        if not matches:
            return None
        return max(matches, key=lambda d: d.created_at)
