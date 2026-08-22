"""LLM-as-judge for ResponseDraft quality (Fase 6.5)."""

from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel, Field

from app.ports.llm_port import LLMPort

SCORING_KEYS = (
    "correctness",
    "completeness",
    "groundedness",
    "tone",
    "actionability",
)


class DraftJudgeOutput(BaseModel):
    correctness: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    groundedness: int = Field(ge=1, le=5)
    tone: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    justification: str


JUDGE_SYSTEM_PROMPT = (
    "You score an accounts-payable draft email. Score based ONLY on the provided "
    "ticket context. Penalise any invented facts that are not in the context. "
    "Each criterion is an integer from 1 (poor) to 5 (excellent)."
)


def _user_prompt(draft_text: str, ticket_context: dict) -> str:
    return (
        "Ticket context (JSON):\n"
        f"{json.dumps(ticket_context, default=str)}\n\n"
        "Draft to score:\n"
        f"{draft_text}\n\n"
        "Score correctness, completeness, groundedness, tone, and actionability."
    )


async def judge_draft(
    draft_text: str,
    ticket_context: dict,
    llm: LLMPort,
) -> dict:
    """Return 1–5 scores plus justification via LLMPort.generate."""
    output = await llm.generate(
        system_prompt=JUDGE_SYSTEM_PROMPT,
        user_prompt=_user_prompt(draft_text, ticket_context),
        output_schema=DraftJudgeOutput,
    )
    if not isinstance(output, DraftJudgeOutput):
        raise TypeError("LLMPort returned an unexpected judge output type")
    scores = {key: getattr(output, key) for key in SCORING_KEYS}
    average = sum(scores.values()) / len(SCORING_KEYS)
    return {**scores, "justification": output.justification, "average": average}


def judge_draft_sync(draft_text: str, ticket_context: dict, llm: LLMPort) -> dict:
    return asyncio.run(judge_draft(draft_text, ticket_context, llm))
