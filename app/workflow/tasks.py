"""Celery worker tasks for the P2P workflow (Fase 5.1).

Start worker (Windows — pool=solo to avoid fork issues):
    celery -A app.workflow.tasks worker --loglevel=info --pool=solo

Start worker (Linux/macOS):
    celery -A app.workflow.tasks worker --loglevel=info
"""

from celery import Celery
from sqlmodel import Session, create_engine

from settings import settings

app = Celery(
    "p2p",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL.replace("/0", "/1"),
)
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"
app.conf.accept_content = ["json"]

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)


def build_workflow_deps(session: Session):
    """Construct WorkflowDeps from environment settings.

    A fresh database session is supplied by each Celery task. SAP and sender
    directory remain fixture-backed until their production integrations land.
    """
    from app.adapters.mock_email import MockEmailAdapter
    from app.adapters.mock_sap import MockSAPAdapter
    from app.adapters.mock_senders import MockSenderDirectory
    from app.adapters.postgres_repos import AuditRepo, DraftRepo, TicketRepo
    from app.domain.deps import WorkflowDeps

    if settings.LLM_PRIMARY_API_KEY:
        from app.adapters.openai_llm import OpenAILLMAdapter

        llm = OpenAILLMAdapter(settings)
    else:
        from app.adapters.mock_llm import MockLLMAdapter

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


@app.task(name="p2p.process_email")
def process_email(raw_payload: dict) -> dict:
    """Celery entry point: run TicketWorkflow for one inbound email payload."""
    from app.workflow.workflow_registry import WorkflowRegistry

    with Session(engine) as session:
        deps = build_workflow_deps(session)
        workflow = WorkflowRegistry.TICKET.value(deps)
        ctx = workflow.run(raw_payload)
        return {
            "ticket_id": str(ctx.ticket.id) if ctx.ticket else None,
            "status": ctx.ticket.status.value if ctx.ticket else None,
        }
