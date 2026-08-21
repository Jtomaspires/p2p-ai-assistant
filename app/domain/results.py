"""Return type for a single workflow node."""


from pydantic import BaseModel, Field

from app.domain.enums import AuditAction


class NodeResult(BaseModel):
    action: AuditAction
    confidence: float | None = None
    metadata: dict = Field(default_factory=dict)
    stop_pipeline: bool = False
