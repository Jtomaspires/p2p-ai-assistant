"""FastAPI application — P2P AI webhook + dashboard HITL endpoints."""

import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api.tickets import router as tickets_router

app = FastAPI(title="P2P AI Assistant", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(tickets_router)


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
    except Exception:  # noqa: BLE001
        from app.workflow.tasks import process_email

        result = process_email(payload)
        return WebhookResponse(
            task_id=str(uuid.uuid4()),
            ticket_id=result["ticket_id"],
            message="processed_sync",
        )
