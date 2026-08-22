"""Day 2 preflight: SQLModel repositories and production LLM adapter behavior."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import BaseModel
from sqlmodel import Session, SQLModel, create_engine

from app.adapters.db_models import InvoiceTable  # noqa: F401
from app.adapters.openai_llm import OpenAILLMAdapter
from app.adapters.postgres_repos import (
    AuditRepo,
    InvoiceRepo,
    SenderDirectoryRepo,
    TicketRepo,
)
from app.domain.enums import AuditAction, InvoiceStage, SenderType
from app.domain.models import AuditEntry, Invoice, RoutingRule, Sender, Ticket
from app.llm.exceptions import LLMUnavailableError
from settings import Settings


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def _ticket() -> Ticket:
    return Ticket(
        thread_id="thread-db",
        message_id="message-db",
        sender_email="billing@acme-supplies.com",
        subject="Invoice",
        body="Status?",
        received_at=datetime(2026, 8, 21, tzinfo=UTC),
    )


def test_ticket_repo_round_trip_and_idempotency_lookups(session):
    repo = TicketRepo(session)
    ticket = repo.create(_ticket())
    assert repo.get_by_id(ticket.id).message_id == ticket.message_id
    assert repo.get_by_message_id("message-db").id == ticket.id
    assert repo.get_by_thread_id("thread-db").id == ticket.id
    assert [item.id for item in repo.list_by_thread_id("thread-db")] == [ticket.id]


def test_sender_directory_and_routing_rule_round_trip(session):
    repo = SenderDirectoryRepo(session)
    sender = Sender(
        id="sender-db",
        email="billing@acme-supplies.com",
        name="Maria",
        company="ACME Supplies Lda",
        vendor_sap_id="10300006",
        sender_type=SenderType.EXTERNAL_SUPPLIER,
    )
    repo.upsert_sender(sender)
    repo.upsert_routing_rule(
        RoutingRule(id="route-db", operator_id="op_ana", domain="acme-supplies.com")
    )
    assert repo.get_by_email(sender.email).id == sender.id
    assert repo.get_by_domain("acme-supplies.com")[0].id == sender.id
    assert (
        repo.get_routing_rule_by_domain("acme-supplies.com").operator_id == "op_ana"
    )


def test_invoice_repo_stores_normalized_reference(session):
    repo = InvoiceRepo(session)
    invoice = Invoice(
        invoice_ref="SCB/1234-345",
        supplier_name="ACME Supplies Lda",
        amount=Decimal("123.00"),
        stage=InvoiceStage.POSTED,
    )
    repo.upsert(invoice)
    matches = repo.get_by_ref_normalized("*SCB1234345*")
    assert len(matches) == 1
    assert matches[0].invoice_ref == invoice.invoice_ref


def test_audit_repo_round_trip(session):
    ticket = TicketRepo(session).create(_ticket())
    repo = AuditRepo(session)
    entry = AuditEntry(
        ticket_id=ticket.id,
        node="ResolutionNode",
        action=AuditAction.RESOLVE,
        confidence=0.95,
        metadata={"match_result": "unique"},
    )
    repo.append(entry)
    stored = repo.get_by_ticket_id(ticket.id)
    assert len(stored) == 1
    assert stored[0].metadata == entry.metadata


class Output(BaseModel):
    value: str


def test_empty_and_placeholder_llm_settings_are_ignored():
    settings = Settings(
        _env_file=None,
        LLM_PRIMARY_API_KEY="test-key",
        LLM_PRIMARY_BASE_URL="",
        LLM_FALLBACK_MODEL="<modelo-fallback>",
        LLM_FALLBACK_API_KEY="<chave-fallback>",
        LLM_FALLBACK_BASE_URL="<endpoint-openai-compatible>",
    )

    assert settings.LLM_PRIMARY_BASE_URL is None
    assert settings.LLM_FALLBACK_MODEL is None
    assert settings.LLM_FALLBACK_API_KEY is None
    assert settings.LLM_FALLBACK_BASE_URL is None


@pytest.mark.asyncio
async def test_production_llm_adapter_requires_local_api_configuration():
    adapter = OpenAILLMAdapter(Settings(_env_file=None))
    with pytest.raises(LLMUnavailableError, match="No LLM endpoint configured"):
        await adapter.generate(
            system_prompt="system",
            user_prompt="user",
            output_schema=Output,
        )


@pytest.mark.asyncio
async def test_production_llm_adapter_retries_then_uses_fallback():
    class StubAdapter(OpenAILLMAdapter):
        def __init__(self, settings):
            super().__init__(settings)
            self.models: list[str] = []

        async def _generate_once(self, *, endpoint, **kwargs):
            self.models.append(endpoint.model)
            if endpoint.model == "primary":
                raise TimeoutError("primary timeout")
            return Output(value="fallback")

    settings = Settings(
        _env_file=None,
        LLM_PRIMARY_MODEL="primary",
        LLM_PRIMARY_API_KEY="test-primary-key",
        LLM_FALLBACK_MODEL="fallback",
        LLM_FALLBACK_API_KEY="test-fallback-key",
        LLM_RETRY_BACKOFF_S=0,
    )
    adapter = StubAdapter(settings)
    result = await adapter.generate(
        system_prompt="system",
        user_prompt="user",
        output_schema=Output,
    )
    assert result == Output(value="fallback")
    assert adapter.models == ["primary", "primary", "fallback"]
