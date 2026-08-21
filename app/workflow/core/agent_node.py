"""Base node for structured LLM calls, adapted from the Launchpad AgentNode pattern."""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.domain.context import ProcessingContext
from app.ports.llm_port import LLMPort
from app.workflow.core.base import Node


class AgentNode(Node, ABC):
    """Base class for nodes that call an LLM with structured output."""

    def __init__(
        self,
        context: ProcessingContext | None = None,
        llm_port: LLMPort | None = None,
    ) -> None:
        super().__init__(context=context)
        self.llm_port = llm_port

    @abstractmethod
    def get_output_schema(self) -> type[BaseModel]:
        """Return the Pydantic model class for this node's LLM output."""
        pass

    @abstractmethod
    def build_system_prompt(self, context: ProcessingContext) -> str:
        pass

    @abstractmethod
    def build_user_prompt(self, context: ProcessingContext) -> str:
        pass

    async def call_llm(self, context: ProcessingContext) -> BaseModel:
        """Build prompts, call the LLM port, and return validated structured output."""
        llm_port = self.llm_port
        if llm_port is None:
            if context.deps is None:
                raise RuntimeError("ProcessingContext.deps is not set")
            llm_port = context.deps.llm
            self.llm_port = llm_port

        return await llm_port.generate(
            system_prompt=self.build_system_prompt(context),
            user_prompt=self.build_user_prompt(context),
            output_schema=self.get_output_schema(),
        )
