"""Inbound event schema for the P2P workflow (Launchpad event_schema analogue)."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class IncomingEmail(BaseModel):
    """Parsed webhook / fixture email that starts a workflow run."""

    thread_id: str | None = None
    message_id: str | None = None
    from_email: str
    subject: str = ""
    body: str = ""
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    attachments: list[dict] = Field(default_factory=list)
    spf_pass: bool | None = None
    dkim_pass: bool | None = None
