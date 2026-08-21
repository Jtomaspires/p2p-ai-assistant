"""Parse raw webhook/fixture dicts into IncomingEmail."""

from datetime import UTC, datetime

from app.domain.events import IncomingEmail
from app.ports.email_port import EmailPort


class MockEmailAdapter(EmailPort):
    def parse_webhook(self, payload: dict) -> IncomingEmail:
        received = payload.get("received_at")
        if isinstance(received, str):
            received_at = datetime.fromisoformat(received.replace("Z", "+00:00"))
        elif isinstance(received, datetime):
            received_at = received
        else:
            received_at = datetime.now(UTC)
        return IncomingEmail(
            thread_id=payload.get("thread_id"),
            message_id=payload.get("message_id"),
            from_email=payload.get("from") or payload.get("from_email") or "",
            subject=payload.get("subject") or "",
            body=payload.get("body") or "",
            received_at=received_at,
            attachments=list(payload.get("attachments") or []),
            spf_pass=payload.get("spf_pass"),
            dkim_pass=payload.get("dkim_pass"),
        )
