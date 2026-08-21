"""Launchpad-style workflow schema (adapted from reference/launchpad/core/schema.py)."""

from typing import Type

from pydantic import BaseModel, ConfigDict, Field

from app.workflow.core.base import Node


class NodeConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    node: Type[Node]
    connections: list[Type[Node]] = Field(default_factory=list)
    is_router: bool = False
    description: str | None = None


class WorkflowSchema(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    description: str | None = None
    event_schema: Type[BaseModel]
    start: Type[Node]
    nodes: list[NodeConfig]
