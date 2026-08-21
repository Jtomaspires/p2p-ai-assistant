from typing import Any, Dict
from pydantic import BaseModel, Field

"""
Task Context Module
This module defines the context object that gets passed between workflow nodes.
It maintains the state and metadata throughout workflow execution.
"""


class TaskContext(BaseModel):
    """Context container for workflow task execution.
    TaskContext maintains the state and results of a workflow's execution,
    tracking the original event, intermediate node results, and additional
    metadata throughout the processing flow.
    Attributes:
        event: The original event that triggered the workflow
        nodes: Dictionary storing results and state from each node's execution
        metadata: Dictionary storing workflow-level metadata and configuration
        should_stop: Boolean flag indicating whether the workflow should stop execution
    Example:
        context = TaskContext(
            event=incoming_event,
            nodes={"AnalyzeNode": {"score": 0.95}},
            metadata={"priority": "high"}
        )
    """

    event: Any
    nodes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Stores results and state from each node's execution",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Stores workflow-level metadata and configuration",
    )
    should_stop: bool = Field(
        default=False,
        description="Flag indicating whether the workflow should stop execution",
    )
    trace_id: str | None = Field(
        default=None,
        description="Langfuse trace ID for this workflow run, captured on entry when tracing is enabled",
    )

    def update_node(self, node_name: str, **kwargs):
        self.nodes[node_name] = {**self.nodes.get(node_name, {}), **kwargs}

    def stop_workflow(self) -> None:
        """Stops the current workflow execution by setting the stop flag.

        This method can be called from any node to halt the workflow processing.
        Once called, the workflow will stop after the current node completes.
        """
        self.should_stop = True
