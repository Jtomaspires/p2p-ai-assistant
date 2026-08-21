"""DAG checks adapted from reference/launchpad/core/validate.py."""

from collections import deque
from typing import Set, Type

from app.workflow.core.base import Node
from app.workflow.core.schema import WorkflowSchema


class WorkflowValidator:
    def __init__(self, workflow_schema: WorkflowSchema):
        self.workflow_schema = workflow_schema

    def validate(self) -> None:
        self._validate_dag()
        self._validate_connections()

    def _validate_dag(self) -> None:
        if self._has_cycle():
            raise ValueError("Workflow schema contains a cycle")
        reachable = self._get_reachable_nodes()
        all_nodes = {nc.node for nc in self.workflow_schema.nodes}
        unreachable = all_nodes - reachable
        if unreachable:
            raise ValueError(f"The following nodes are unreachable: {unreachable}")

    def _has_cycle(self) -> bool:
        visited: set[Type[Node]] = set()
        rec_stack: set[Type[Node]] = set()

        def dfs(node: Type[Node]) -> bool:
            visited.add(node)
            rec_stack.add(node)
            node_config = next(
                (nc for nc in self.workflow_schema.nodes if nc.node == node),
                None,
            )
            if node_config:
                for neighbor in node_config.connections:
                    if neighbor not in visited:
                        if dfs(neighbor):
                            return True
                    elif neighbor in rec_stack:
                        return True
            rec_stack.remove(node)
            return False

        for node_config in self.workflow_schema.nodes:
            if node_config.node not in visited and dfs(node_config.node):
                return True
        return False

    def _get_reachable_nodes(self) -> Set[Type[Node]]:
        reachable: set[Type[Node]] = set()
        queue = deque([self.workflow_schema.start])
        while queue:
            node = queue.popleft()
            if node not in reachable:
                reachable.add(node)
                node_config = next(
                    (nc for nc in self.workflow_schema.nodes if nc.node == node),
                    None,
                )
                if node_config:
                    queue.extend(node_config.connections)
        return reachable

    def _validate_connections(self) -> None:
        for node_config in self.workflow_schema.nodes:
            if len(node_config.connections) > 1 and not node_config.is_router:
                raise ValueError(
                    f"Node {node_config.node.__name__} has multiple connections "
                    "but is not marked as a router."
                )
