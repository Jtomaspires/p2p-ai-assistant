"""Pydantic request/response models for dashboard HITL endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ApproveBody(BaseModel):
    operator_id: str
    final_text: str | None = None


class EscalateBody(BaseModel):
    operator_id: str


class TicketListItem(BaseModel):
    id: UUID
    received_at: datetime
    sender_email: str
    sender_name: str | None = None
    sender_company: str | None = None
    subject: str
    intent: str | None = None
    status: str
    confidence: float | None = None
    assigned_operator_id: str | None = None


class AuditSummary(BaseModel):
    node: str
    action: str
    confidence: float | None = None
    created_at: datetime


class TicketDetail(BaseModel):
    ticket: dict[str, Any]
    sender: dict[str, Any] | None = None
    draft: dict[str, Any] | None = None
    invoice: dict[str, Any] | None = None
    audit: list[AuditSummary] = Field(default_factory=list)


class HitlActionResult(BaseModel):
    ticket: dict[str, Any]
    draft: dict[str, Any] | None = None
    human_review: dict[str, Any] | None = None
