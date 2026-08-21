"""Deterministic structured-output LLM adapter for tests."""

from collections import deque
from typing import Any

from pydantic import BaseModel

from app.ports.llm_port import LLMPort


class MockLLMAdapter(LLMPort):
    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self._queue: deque[dict[str, Any]] = deque(responses or [])
        self.calls: list[dict[str, Any]] = []

    def enqueue(self, response: dict[str, Any]) -> None:
        self._queue.append(response)

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "output_schema": output_schema,
            }
        )
        if not self._queue:
            raise RuntimeError("MockLLMAdapter has no queued responses")
        return output_schema.model_validate(self._queue.popleft())
