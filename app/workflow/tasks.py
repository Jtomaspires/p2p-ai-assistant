"""Celery worker tasks for the P2P workflow (Fase 5.1).

Start worker (Windows — pool=solo to avoid fork issues):
    celery -A app.workflow.tasks worker --loglevel=info --pool=solo

Start worker (Linux/macOS):
    celery -A app.workflow.tasks worker --loglevel=info
"""

from celery import Celery

from settings import settings

app = Celery(
    "p2p",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL.replace("/0", "/1"),
)
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"
app.conf.accept_content = ["json"]


def build_workflow_deps():
    """Construct WorkflowDeps from environment settings.

    Uses in-memory adapters for everything except the LLM (which uses the
    configured OpenAI-compatible adapter when API key is present).
    """
    from app.adapters.memory_audit import InMemoryAuditLog
    from app.adapters.memory_draft import InMemoryDraftStore
    from app.adapters.memory_ticket_store import InMemoryTicketStore
    from app.adapters.mock_email import MockEmailAdapter
    from app.adapters.mock_sap import MockSAPAdapter
    from app.adapters.mock_senders import MockSenderDirectory
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
        tickets=InMemoryTicketStore(),
        sap=MockSAPAdapter(),
        audit=InMemoryAuditLog(),
        senders=MockSenderDirectory(),
        drafts=InMemoryDraftStore(),
    )


@app.task(name="p2p.process_email")
def process_email(raw_payload: dict) -> dict:
    """Celery entry point: run TicketWorkflow for one inbound email payload."""
    from app.workflow.workflow_registry import WorkflowRegistry

    deps = build_workflow_deps()
    workflow = WorkflowRegistry.TICKET.value(deps)
    ctx = workflow.run(raw_payload)
    return {
        "ticket_id": str(ctx.ticket.id) if ctx.ticket else None,
        "status": ctx.ticket.status.value if ctx.ticket else None,
    }
