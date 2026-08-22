"""Node 1 — ingest webhook payload (Fase 3.1)."""

from datetime import UTC, datetime

from app.domain.context import ProcessingContext
from app.domain.enums import AuditAction, TicketStatus
from app.domain.models import Ticket
from app.domain.results import NodeResult
from app.workflow.core.base import Node
from app.workflow.nodes._helpers import finish, require_deps


class IngestionNode(Node):
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        self.context = context
        deps = require_deps(context)
        event = context.event
        if event is None:
            event = deps.email.parse_webhook({})
            context.event = event

        if not event.message_id or not event.thread_id:
            result = NodeResult(
                action=AuditAction.INGEST,
                metadata={"reason": "ingest_rejected"},
                stop_pipeline=True,
            )
            self.save_output(result)
            return finish(context, result)

        existing = deps.tickets.get_by_message_id(event.message_id)
        if existing is not None:
            context.ticket = existing
            result = NodeResult(
                action=AuditAction.INGEST,
                metadata={"reason": "duplicate_ignored", "message_id": event.message_id},
                stop_pipeline=True,
            )
            self.save_output(result)
            return finish(context, result)

        attachments = []
        for raw in event.attachments:
            name = str(raw if isinstance(raw, str) else raw.get("filename", "")).lower()
            is_pdf = name.endswith(".pdf") or (isinstance(raw, dict) and str(raw.get("content_type", "")).endswith("pdf"))
            if not is_pdf and name and not name.endswith(".pdf"):
                continue
            is_invoice = "inv" in name or "invoice" in name or "fatura" in name
            attachments.append({"filename": name, "is_invoice": is_invoice})

        context.ticket = Ticket(
            thread_id=event.thread_id,
            message_id=event.message_id,
            sender_email=event.from_email,
            subject=event.subject,
            body=event.body,
            received_at=event.received_at or datetime.now(UTC),
            status=TicketStatus.OPEN,
        )
        # Persist before Workflow records this node's audit entry. PostgreSQL
        # enforces the audit_entries.ticket_id foreign key.
        deps.tickets.save_ticket(context.ticket)
        result = NodeResult(
            action=AuditAction.INGEST,
            confidence=1.0,
            metadata={"attachments": attachments, "empty_body": not bool(event.body.strip())},
        )
        self.save_output(result)
        return finish(context, result)
