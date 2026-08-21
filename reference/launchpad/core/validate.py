from collections import deque
from typing import Set, Type

from launchpad.core.nodes.base import Node
from launchpad.core.schema import WorkflowSchema

"""
Workflow Validator Module

This module provides validation logic for workflow schemas.
It ensures that workflows form valid directed acyclic graphs (DAGs)
and that routing configurations are correct.
"""


class WorkflowValidator:
    """Validator for ensuring workflow schema correctness.

    The WorkflowValidator performs comprehensive validation of workflow schemas,
    checking for cycles, unreachable nodes, and proper routing configurations.
    It ensures that the workflow forms a valid directed acyclic graph (DAG)
    and that routing nodes are properly configured.

    Attributes:
        workflow_schema: The WorkflowSchema to validate

    Example:
        validator = WorkflowValidator(workflow_schema)
        validator.validate()  # Raises ValueError if validation fails
    """

    def __init__(self, workflow_schema: WorkflowSchema):
        """Initializes the validator with a workflow schema.

        Args:
            workflow_schema: The WorkflowSchema to validate
        """
        self.workflow_schema = workflow_schema

    def validate(self):
        """Validates all aspects of the workflow schema.

        Performs comprehensive validation including DAG structure
        and routing configuration checks.

        Raises:
            ValueError: If any validation check fails
        """
        self._validate_dag()
        self._validate_connections()

    def _validate_dag(self):
        """Validates that the workflow schema forms a proper DAG.

        Checks for cycles and ensures all nodes are reachable
        from the start node.

        Raises:
            ValueError: If the workflow contains cycles or unreachable nodes
        """
        if self._has_cycle():
            raise ValueError("Workflow schema contains a cycle")

        reachable_nodes = self._get_reachable_nodes()
        all_nodes = set(nc.node for nc in self.workflow_schema.nodes)
        unreachable_nodes = all_nodes - reachable_nodes
        if unreachable_nodes:
            raise ValueError(
                f"The following nodes are unreachable: {unreachable_nodes}"
            )

    def _has_cycle(self) -> bool:
        """Detects cycles in the workflow graph using DFS.

        Returns:
            bool: True if a cycle is detected, False otherwise
        """
        visited = set()
        rec_stack = set()

        def dfs(node: Type[Node]) -> bool:
            visited.add(node)
            rec_stack.add(node)

            node_config = next(
                (nc for nc in self.workflow_schema.nodes if nc.node == node), None
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
            if node_config.node not in visited:
                if dfs(node_config.node):
                    return True

        return False

    def _get_reachable_nodes(self) -> Set[Type[Node]]:
        """Identifies all nodes reachable from the start node using BFS.

        Returns:
            Set[Type[Node]]: Set of all reachable node classes
        """
        reachable = set()
        queue = deque([self.workflow_schema.start])

        while queue:
            node = queue.popleft()
            if node not in reachable:
                reachable.add(node)
                node_config = next(
                    (nc for nc in self.workflow_schema.nodes if nc.node == node), None
                )
                if node_config:
                    queue.extend(node_config.connections)

        return reachable

    def _validate_connections(self):
        """Validates node connection configurations.

        Ensures that only nodes marked as routers have multiple connections.

        Raises:
            ValueError: If a non-router node has multiple connections
        """
        for node_config in self.workflow_schema.nodes:
            if len(node_config.connections) > 1 and not node_config.is_router:
                raise ValueError(
                    f"Node {node_config.node.__name__} has multiple connections but is not marked as a router."
                )
