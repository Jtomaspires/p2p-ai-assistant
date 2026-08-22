"""FastAPI session wiring and shared WorkflowDeps factory (also used by Celery)."""

from collections.abc import Iterator

from sqlmodel import Session, create_engine

from settings import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def build_workflow_deps(session: Session):
    """Construct WorkflowDeps from environment settings.

    A fresh database session is supplied by each Celery task or API request.
    SAP and sender directory remain fixture-backed until production integrations land.
    """
    from app.adapters.mock_email import MockEmailAdapter
    from app.adapters.mock_llm import MockLLMAdapter
    from app.adapters.mock_sap import MockSAPAdapter
    from app.adapters.mock_senders import MockSenderDirectory
    from app.adapters.postgres_repos import AuditRepo, DraftRepo, TicketRepo
    from app.domain.deps import WorkflowDeps

    if settings.LLM_PRIMARY_API_KEY:
        from app.adapters.openai_llm import OpenAILLMAdapter

        llm = OpenAILLMAdapter(settings)
    else:
        llm = MockLLMAdapter()

    return WorkflowDeps(
        settings=settings,
        llm=llm,
        email=MockEmailAdapter(),
        tickets=TicketRepo(session),
        sap=MockSAPAdapter(),
        audit=AuditRepo(session),
        senders=MockSenderDirectory(),
        drafts=DraftRepo(session),
    )
