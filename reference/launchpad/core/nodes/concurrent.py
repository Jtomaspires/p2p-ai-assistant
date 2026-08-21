import asyncio
from abc import ABC, abstractmethod

from launchpad.core.nodes.base import Node
from launchpad.core.schema import NodeConfig
from launchpad.core.task import TaskContext


class ConcurrentNode(Node, ABC):
    """
    Base class for nodes that execute other nodes concurrently using asyncio.

    This class provides a method to execute a list of nodes concurrently on a single thread,
    using asyncio.gather. This ensures that I/O-bound operations can proceed in parallel
    without blocking the main thread or event loop.

    Subclasses must implement the `process` method to define the specific logic of the concurrent node.
    """

    async def execute_nodes_concurrently(self, task_context: TaskContext):
        node_config: NodeConfig = task_context.metadata["nodes"][self.__class__]
        coroutines = [
            node(task_context).process(task_context)
            for node in node_config.concurrent_nodes
        ]
        return await asyncio.gather(*coroutines)

    @abstractmethod
    async def process(self, task_context: TaskContext) -> TaskContext:
        pass
