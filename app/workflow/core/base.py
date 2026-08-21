"""Node and router bases adapted from reference/launchpad/core/nodes/."""

from abc import ABC, abstractmethod
from typing import Optional, Type

from pydantic import BaseModel

from app.domain.context import ProcessingContext


class Node(ABC):
    class OutputType(BaseModel):
        pass

    def __init__(self, context: ProcessingContext | None = None):
        self.context = context

    def save_output(self, output: BaseModel) -> None:
        if self.context is None:
            raise RuntimeError("Node has no processing context")
        self.context.nodes[self.node_name] = output

    def get_output(self, node_class: Type["Node"]) -> Optional[BaseModel]:
        if self.context is None:
            return None
        return self.context.nodes.get(node_class.__name__)

    @property
    def node_name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        pass

    async def cleanup(self) -> None:
        return None


class RouterNode(ABC):
    def __init__(self, context: ProcessingContext | None = None):
        self.context = context

    @abstractmethod
    def determine_next_node(self, context: ProcessingContext) -> Optional[Node]:
        pass

    @property
    def node_name(self) -> str:
        return self.__class__.__name__

    def save_output(self, output: BaseModel) -> None:
        if self.context is None:
            raise RuntimeError("RouterNode has no processing context")
        self.context.nodes[self.node_name] = output


class BaseRouter(Node):
    """Graph node that classifies then selects the next Node via RouterNode rules."""

    routes: list[RouterNode] = []
    fallback: Node | None = None

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        return context

    def route(self, context: ProcessingContext) -> Node | None:
        for route_node in self.routes:
            route_node.context = context
            next_node = route_node.determine_next_node(context)
            if next_node:
                return next_node
        return self.fallback
