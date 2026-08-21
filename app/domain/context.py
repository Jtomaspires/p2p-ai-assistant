"""Ephemeral processing state passed between workflow nodes."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.events import IncomingEmail
from app.domain.models import Invoice, ResponseDraft, Sender, Ticket
from app.domain.results import NodeResult


class ProcessingContext(BaseModel):
    """Lives only for the duration of one ticket run. Not persisted.

    Combines P2P domain state with Launchpad TaskContext fields
    (`event`, `nodes`, `should_stop`) so Workflow.run can drive the graph.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ticket: Ticket | None = None
    sender: Sender | None = None
    invoice: Invoice | None = None
    draft: ResponseDraft | None = None
    extracted_ref: str | None = None
    extracted_amount: Decimal | None = None
    is_thread_continuation: bool = False
    confidence_components: dict = Field(default_factory=dict)
    skip_identity: bool = False
    event: IncomingEmail | None = None
    nodes: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    should_stop: bool = False
    last_result: NodeResult | None = None
    deps: Any = None

    def stop_workflow(self) -> None:
        self.should_stop = True
