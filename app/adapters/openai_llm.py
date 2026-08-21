"""OpenAI-compatible production adapter for the structured-output LLM port."""

import asyncio
import json
from dataclasses import dataclass

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.llm.exceptions import LLMUnavailableError
from app.ports.llm_port import LLMPort
from settings import Settings


@dataclass(frozen=True)
class _Endpoint:
    model: str
    api_key: str
    base_url: str | None


class OpenAILLMAdapter(LLMPort):
    """Call a primary endpoint, retry once, then try an optional fallback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        endpoints = self._configured_endpoints()
        errors: list[str] = []

        for endpoint in endpoints:
            for attempt in range(2):
                try:
                    return await self._generate_once(
                        endpoint=endpoint,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        output_schema=output_schema,
                    )
                except Exception as exc:
                    errors.append(
                        f"{endpoint.model} attempt {attempt + 1}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    if attempt == 0:
                        await asyncio.sleep(self.settings.LLM_RETRY_BACKOFF_S)

        detail = "; ".join(errors)
        raise LLMUnavailableError(f"All configured LLM endpoints failed. {detail}")

    def _configured_endpoints(self) -> list[_Endpoint]:
        endpoints: list[_Endpoint] = []
        if self.settings.LLM_PRIMARY_API_KEY:
            endpoints.append(
                _Endpoint(
                    model=self.settings.LLM_PRIMARY_MODEL,
                    api_key=self.settings.LLM_PRIMARY_API_KEY,
                    base_url=self.settings.LLM_PRIMARY_BASE_URL,
                )
            )
        if self.settings.LLM_FALLBACK_MODEL and self.settings.LLM_FALLBACK_API_KEY:
            endpoints.append(
                _Endpoint(
                    model=self.settings.LLM_FALLBACK_MODEL,
                    api_key=self.settings.LLM_FALLBACK_API_KEY,
                    base_url=self.settings.LLM_FALLBACK_BASE_URL,
                )
            )
        if not endpoints:
            raise LLMUnavailableError(
                "No LLM endpoint configured. Set LLM_PRIMARY_API_KEY (and optionally "
                "LLM_FALLBACK_MODEL / LLM_FALLBACK_API_KEY) in the local .env file."
            )
        return endpoints

    async def _generate_once(
        self,
        *,
        endpoint: _Endpoint,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        client = AsyncOpenAI(api_key=endpoint.api_key, base_url=endpoint.base_url)
        schema = output_schema.model_json_schema()
        response = await client.chat.completions.create(
            model=endpoint.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{system_prompt}\n\nReturn JSON matching this schema exactly:\n"
                        f"{json.dumps(schema)}"
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            timeout=self.settings.LLM_TIMEOUT_S,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned an empty response")
        return output_schema.model_validate_json(content)
