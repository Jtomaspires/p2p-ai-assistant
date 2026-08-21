from abc import ABC, abstractmethod
from typing import Type, Optional

from pydantic import BaseModel

from launchpad.core.task import TaskContext

"""
Base Node Module

This module defines the foundational Node class that all workflow nodes inherit from.
It implements the Chain of Responsibility pattern, allowing nodes to process tasks
sequentially and pass results to the next node in the chain.
"""


class Node(ABC):
    class OutputType(BaseModel):
        """
        OutputType class for representing structured outputs for Nodes.
        """

        pass

    def __init__(self, task_context: TaskContext = None):
        """
        The constructor is used to initialize the class with a provided TaskContext
        instance or without any context.

        Parameters:
        task_context (TaskContext, optional): Context associated with the task.
            Defaults to None.
        """
        self.task_context = task_context

    def save_output(self, output: BaseModel):
        """
        Saves the output of a task node into the task context, associating it with the
        node's name for future reference.

        Args:
            output (BaseModel): The model instance representing the result of the task
            to be stored in the task_context.
        """
        self.task_context.nodes[self.node_name] = output

    def get_output(self, node_class: Type["Node"]) -> Optional[OutputType]:
        """
        Retrieves the output associated with a specific node class from the task context.

        Parameters:
        node_class: Type[Node]
            The class of the node whose output is to be retrieved.

        Returns:
        Optional[OutputType]
            The output associated with the specified node class if it exists, otherwise None.
        """
        return self.task_context.nodes.get(node_class.__name__, None)

    @property
    def node_name(self) -> str:
        """Gets the name of the node.

        Returns:
            String name derived from the class name
        """
        return self.__class__.__name__

    @abstractmethod
    async def process(self, task_context: TaskContext) -> TaskContext:
        """Processes the task context in the responsibility chain.

        This method implements the Chain of Responsibility pattern's handle
        method. Each node in the workflow processes the task and passes it
        to the next node through the workflow orchestrator.

        Args:
            task_context: The shared context object passed through the workflow

        Returns:
            Updated TaskContext with this node's processing results

        Note:
            Implementations should:
            1. Process the task according to their specific responsibility
            2. Store results using the save_output method
        """
        pass

    async def cleanup(self) -> None:
        """Releases any per-instance resources held by the node.

        Called after the node finishes processing, including when an
        exception propagates out. Override this when the node holds
        clients or connections that need explicit teardown between runs
        (for example, when the same node type is re-entered by a child
        workflow during composition).
        """
        pass
