"""Workflow orchestrator adapted from reference/launchpad/core/workflow.py."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC
from typing import Any, ClassVar, Type
from uuid import UUID

from app.domain.context import ProcessingContext
from app.domain.deps import WorkflowDeps
from app.domain.enums import AuditAction
from app.domain.models import AuditEntry
from app.domain.results import NodeResult
from app.workflow.core.base import BaseRouter, Node
from app.workflow.core.schema import NodeConfig, WorkflowSchema
from app.workflow.core.validate import WorkflowValidator


class Workflow(ABC):
    workflow_schema: ClassVar[WorkflowSchema]

    def __init__(self, deps: WorkflowDeps):
        self.validator = WorkflowValidator(self.workflow_schema)
        self.validator.validate()
        self.nodes: dict[Type[Node], NodeConfig] = self._initialize_nodes()
        self.deps = deps

    def _initialize_nodes(self) -> dict[Type[Node], NodeConfig]:
        nodes: dict[Type[Node], NodeConfig] = {}
        for node_config in self.workflow_schema.nodes:
            nodes[node_config.node] = node_config
            for connected_node in node_config.connections:
                if connected_node not in nodes:
                    nodes[connected_node] = NodeConfig(node=connected_node)
        return nodes

    def run(self, event: dict[str, Any] | None = None, *, context: ProcessingContext | None = None) -> ProcessingContext:
        if context is None and event is None:
            raise ValueError("Either event or context must be provided")
        return asyncio.run(self.run_async(event, context=context))

    async def run_async(
        self,
        event: dict[str, Any] | None = None,
        *,
        context: ProcessingContext | None = None,
    ) -> ProcessingContext:
        if context is None and event is None:
            raise ValueError("Either event or context must be provided")
        return await self._run(event, context)

    async def _run(
        self,
        event: dict[str, Any] | None,
        existing_context: ProcessingContext | None,
    ) -> ProcessingContext:
        if existing_context is not None:
            context = existing_context
            context.should_stop = False
        else:
            parsed = self.workflow_schema.event_schema.model_validate(event)
            context = ProcessingContext(event=parsed, deps=self.deps)

        context.deps = self.deps
        current_node_class: Type[Node] | None = self.workflow_schema.start

        while current_node_class:
            if context.should_stop:
                logging.info("Stopping workflow execution")
                break

            node_config = self.nodes[current_node_class]
            node_instance = node_config.node(context=context)
            context = await node_instance.process(context)
            self._record_audit(context, node_instance.node_name)
            await node_instance.cleanup()

            current_node_class = await self._get_next_node_class(current_node_class, context)

        return context

    async def _get_next_node_class(
        self,
        current_node_class: Type[Node],
        context: ProcessingContext,
    ) -> Type[Node] | None:
        node_config = next(
            (nc for nc in self.workflow_schema.nodes if nc.node == current_node_class),
            None,
        )
        if not node_config or not node_config.connections:
            return None
        if node_config.is_router:
            router = current_node_class(context=context)
            if not isinstance(router, BaseRouter):
                raise TypeError(f"{current_node_class.__name__} is marked is_router but is not a BaseRouter")
            next_node = router.route(context)
            return next_node.__class__ if next_node else None
        return node_config.connections[0]

    def _record_audit(self, context: ProcessingContext, node_name: str) -> None:
        result: NodeResult | None = context.last_result
        if result is None:
            return
        ticket_id = context.ticket.id if context.ticket else UUID(int=0)
        self.deps.audit.append(
            AuditEntry(
                ticket_id=ticket_id,
                node=node_name,
                action=result.action,
                confidence=result.confidence,
                metadata=result.metadata,
            )
        )
        if result.stop_pipeline:
            context.stop_workflow()
