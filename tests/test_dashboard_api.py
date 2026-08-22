"""Test Gate 1 — dashboard FastAPI endpoints (Fase 4.1)."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlmodel import Session

from app.adapters.postgres_repos import DraftRepo, TicketRepo
from app.api.deps import get_session
from app.api.main import app
from app.domain.enums import DraftTarget, Intent, TicketStatus
from app.domain.models import ResponseDraft, Ticket


@pytest.fixture
async def client(db_session: Session) -> AsyncIterator[httpx.AsyncClient]:
    def override_get_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _ticket(**overrides) -> Ticket:
    payload = {
        "thread_id": f"thread-{uuid4()}",
        "message_id": f"msg-{uuid4()}",
        "sender_email": "billing@acme-supplies.com",
        "subject": "Invoice INV-2026-0001",
        "body": "Please confirm payment status.",
        "received_at": datetime(2026, 8, 21, tzinfo=UTC),
        "status": TicketStatus.AWAITING_HUMAN,
        "intent": Intent.PAYMENT_STATUS,
        "confidence": 0.91,
        "assigned_operator_id": "op_joao",
    }
    payload.update(overrides)
    return Ticket.model_validate(payload)


def _draft(ticket_id, **overrides) -> ResponseDraft:
    payload = {
        "ticket_id": ticket_id,
        "target": DraftTarget.SENDER,
        "to_email": "billing@acme-supplies.com",
        "generated_text": "Your invoice has been paid.",
    }
    payload.update(overrides)
    return ResponseDraft.model_validate(payload)


def _seed_ticket(session: Session, **overrides) -> Ticket:
    return TicketRepo(session).save_ticket(_ticket(**overrides))


def _seed_ticket_with_draft(
    session: Session, **overrides
) -> tuple[Ticket, ResponseDraft]:
    ticket = _seed_ticket(session, **overrides)
    draft = DraftRepo(session).save_draft(_draft(ticket.id))
    return ticket, draft


async def test_health_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_list_tickets_returns_list(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    _seed_ticket(db_session, status=TicketStatus.OPEN)
    response = await client.get("/tickets")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1


async def test_list_tickets_filters_awaiting_human(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    _seed_ticket(db_session, status=TicketStatus.AWAITING_HUMAN)
    _seed_ticket(db_session, status=TicketStatus.RESOLVED)
    response = await client.get("/tickets", params={"status": "awaiting_human"})
    assert response.status_code == 200
    body = response.json()
    assert body
    assert all(item["status"] == "awaiting_human" for item in body)


async def test_list_tickets_filters_assigned_operator(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    _seed_ticket(db_session, assigned_operator_id="op_joao")
    _seed_ticket(db_session, assigned_operator_id="op_ana")
    response = await client.get("/tickets", params={"assigned_operator_id": "op_joao"})
    assert response.status_code == 200
    body = response.json()
    assert body
    assert all(item["assigned_operator_id"] == "op_joao" for item in body)


async def test_get_ticket_includes_detail_keys(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    ticket, _ = _seed_ticket_with_draft(db_session)
    response = await client.get(f"/tickets/{ticket.id}")
    assert response.status_code == 200
    body = response.json()
    assert "ticket" in body
    assert "draft" in body
    assert "invoice" in body
    assert body["ticket"]["id"] == str(ticket.id)


async def test_get_ticket_unknown_id_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/tickets/{uuid4()}")
    assert response.status_code == 404


async def test_get_draft_200_when_present(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    ticket, draft = _seed_ticket_with_draft(db_session)
    response = await client.get(f"/tickets/{ticket.id}/draft")
    assert response.status_code == 200
    assert response.json()["id"] == str(draft.id)
    assert response.json()["generated_text"] == draft.generated_text


async def test_get_draft_404_when_missing(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    ticket = _seed_ticket(db_session)
    response = await client.get(f"/tickets/{ticket.id}/draft")
    assert response.status_code == 404


async def test_get_draft_unknown_ticket_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/tickets/{uuid4()}/draft")
    assert response.status_code == 404


async def test_approve_without_final_text_resolves(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    ticket, _ = _seed_ticket_with_draft(db_session)
    response = await client.post(
        f"/tickets/{ticket.id}/approve",
        json={"operator_id": "op_joao"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ticket"]["status"] == TicketStatus.RESOLVED.value
    assert body["human_review"]["action"] == "approved"


async def test_approve_with_final_text_marks_edit(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    ticket, _ = _seed_ticket_with_draft(db_session)
    response = await client.post(
        f"/tickets/{ticket.id}/approve",
        json={"operator_id": "op_joao", "final_text": "edited text"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["draft"]["final_text"] == "edited text"
    assert body["draft"]["edited_by_human"] is True
    assert body["human_review"]["action"] == "approved_with_edit"
    assert body["ticket"]["status"] == TicketStatus.RESOLVED.value


async def test_escalate_sets_escalated(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    ticket, _ = _seed_ticket_with_draft(db_session)
    response = await client.post(
        f"/tickets/{ticket.id}/escalate",
        json={"operator_id": "op_joao"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ticket"]["status"] == TicketStatus.ESCALATED.value
    assert body["human_review"]["action"] == "escalated_to_email"


async def test_stats_has_integer_counts_per_status(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    _seed_ticket(db_session, status=TicketStatus.AWAITING_HUMAN)
    _seed_ticket(db_session, status=TicketStatus.RESOLVED)
    response = await client.get("/stats")
    assert response.status_code == 200
    body = response.json()
    for status in TicketStatus:
        assert status.value in body
        assert isinstance(body[status.value], int)
    assert body["awaiting_human"] >= 1
    assert body["resolved"] >= 1


async def test_approve_already_resolved_returns_409(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    ticket, _ = _seed_ticket_with_draft(db_session, status=TicketStatus.RESOLVED)
    response = await client.post(
        f"/tickets/{ticket.id}/approve",
        json={"operator_id": "op_joao"},
    )
    assert response.status_code == 409


async def test_escalate_already_resolved_returns_409(
    client: httpx.AsyncClient, db_session: Session
) -> None:
    ticket, _ = _seed_ticket_with_draft(db_session, status=TicketStatus.RESOLVED)
    response = await client.post(
        f"/tickets/{ticket.id}/escalate",
        json={"operator_id": "op_joao"},
    )
    assert response.status_code == 409
