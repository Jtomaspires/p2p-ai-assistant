from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any

from launchpad.core.nodes.agent import AgentNode
from launchpad.core.task import TaskContext


class AgentStreamingNode(AgentNode, ABC):
    def __init__(self, task_context: TaskContext = None):
        super().__init__(task_context=task_context)

    @abstractmethod
    async def process(self, task_context: TaskContext) -> AsyncIterator[Dict[str, Any]]:
        async with self.agent.run_stream("") as result:
            async for chunk in self.stream_text_deltas(result):
                yield chunk

    async def stream_text_deltas(
        self,
        stream_result,
        debounce_by: float = 0.01,
    ) -> AsyncIterator[dict]:
        previous_text = ""
        async for text_chunk in stream_result.stream_text(debounce_by=debounce_by):
            if text_chunk.startswith(previous_text):
                delta_text = text_chunk[len(previous_text) :]
            else:
                delta_text = text_chunk
            if not delta_text:
                continue
            previous_text = text_chunk
            yield self.completion_chunk(delta_text)

    async def stream_structured_deltas(
        self,
        stream_result,
        debounce_by: float = 0.01,
    ):
        async for chunk in stream_result.stream_output(debounce_by=debounce_by):
            if chunk.model_dump():
                yield self.completion_chunk(chunk.model_dump())

    def completion_chunk(self, content: str) -> dict:
        return {
            "object": "chat.completion.chunk",
            "model": "default",
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": content},
                    "finish_reason": None,
                }
            ],
        }
