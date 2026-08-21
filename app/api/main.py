"""FastAPI application — P2P AI webhook + health endpoints."""

import uuid

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="P2P AI Assistant", version="0.1.0")


class WebhookResponse(BaseModel):
    task_id: str
    ticket_id: str | None = None
    message: str = "accepted"


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook/mock", response_model=WebhookResponse)
def webhook_mock(payload: dict) -> WebhookResponse:
    """Accept an email fixture JSON and dispatch a Celery task.

    Returns the Celery task ID so the caller can poll for the result.
    Falls back to synchronous local run when Celery broker is unavailable.
    """
    try:
        from app.workflow.tasks import process_email

        task = process_email.delay(payload)
        return WebhookResponse(task_id=str(task.id))
    except Exception:
        # Broker not available — run synchronously for dev/test convenience
        from app.workflow.tasks import build_workflow_deps, process_email  # noqa: F811
        from app.workflow.workflow_registry import WorkflowRegistry

        deps = build_workflow_deps()
        workflow = WorkflowRegistry.TICKET.value(deps)
        ctx = workflow.run(payload)
        ticket_id = str(ctx.ticket.id) if ctx.ticket else None
        return WebhookResponse(
            task_id=str(uuid.uuid4()),
            ticket_id=ticket_id,
            message="processed_sync",
        )
