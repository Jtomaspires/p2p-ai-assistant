"""LLM completion port."""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMPort(ABC):
    @abstractmethod
    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        """Generate and validate structured output against a Pydantic schema."""
