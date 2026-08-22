"""Celery worker tasks for the P2P workflow (Fase 5.1).

Start worker (Windows — pool=solo to avoid fork issues):
    celery -A app.workflow.tasks worker --loglevel=info --pool=solo

Start worker (Linux/macOS):
    celery -A app.workflow.tasks worker --loglevel=info
"""

from celery import Celery
from sqlmodel import Session

from app.api.deps import build_workflow_deps, engine
from settings import settings

app = Celery(
    "p2p",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL.replace("/0", "/1"),
)
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"
app.conf.accept_content = ["json"]


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
