"""Golden-dataset eval runner (Fase 6).

Calls TicketWorkflow(deps).run(...) synchronously (no Celery).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llm.judge import judge_draft_sync
from app.ports.llm_port import LLMPort
from scripts.eval_harness import FixtureGuidedLLM, load_fixtures, run_fixture
from settings import settings as app_settings

DEFAULT_OUTPUT_DIR = ROOT / "golden_dataset" / "baselines"
DIMENSIONS = (
    "intent",
    "ticket_status",
    "invoice_resolution",
    "draft_target",
    "to_email",
    "attach_payment_proof",
    "human_action_needed",
)
WORKFLOW_SUCCESS_THRESHOLD = 0.80


def _output_dir() -> Path:
    return Path(os.environ.get("EVAL_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))


def _norm(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value
    return value


def _compare(expected: dict, actual: dict) -> dict[str, bool]:
    matches = {}
    for key in DIMENSIONS:
        matches[f"{key}_match"] = _norm(expected.get(key)) == _norm(actual.get(key))
    return matches


def _judge_llm() -> LLMPort:
    if os.environ.get("EVAL_LIVE_LLM") and app_settings.LLM_PRIMARY_API_KEY:
        from app.adapters.openai_llm import OpenAILLMAdapter

        return OpenAILLMAdapter(app_settings)
    return FixtureGuidedLLM()


def run_eval(*, judge_llm: LLMPort | None = None) -> dict:
    fixtures = load_fixtures()
    llm = judge_llm or _judge_llm()
    failures: list[str] = []
    dim_hits = {key: 0 for key in DIMENSIONS}
    quality_scores: list[float] = []
    n = 0

    for filename, fixture in fixtures:
        n += 1
        expected = fixture["expected"]
        _ctx, actual = run_fixture(fixture)
        matches = _compare(expected, actual)
        for key in DIMENSIONS:
            if matches[f"{key}_match"]:
                dim_hits[key] += 1
        if not all(matches.values()):
            reasons = [k for k, ok in matches.items() if not ok]
            failures.append(f"{fixture.get('id', filename)}: {', '.join(reasons)}")

        if expected.get("draft_target") is not None and actual.get("generated_text"):
            ticket_context = {
                "expected": expected,
                "actual_status": actual.get("ticket_status"),
                "invoice_resolution": actual.get("invoice_resolution"),
            }
            judged = judge_draft_sync(actual["generated_text"], ticket_context, llm)
            quality_scores.append(float(judged["average"]))

    def rate(hits: int) -> float:
        return hits / n if n else 0.0

    report = {
        "run_id": f"{datetime.now(UTC).date().isoformat()}_v1",
        "model": app_settings.LLM_PRIMARY_MODEL,
        "workflow_success_rate": (n - len(failures)) / n if n else 0.0,
        "intent_accuracy": rate(dim_hits["intent"]),
        "resolution_accuracy": rate(dim_hits["invoice_resolution"]),
        "draft_target_accuracy": rate(dim_hits["draft_target"]),
        "draft_quality_avg": (
            sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
        ),
        "failures": failures,
        "notes": (
            "Deterministic FixtureGuidedLLM (set EVAL_LIVE_LLM=1 plus API key for live judge). "
            "Thread fixtures run as new tickets (extracted_ref is ephemeral)."
        ),
    }
    return report


def write_report(report: dict, output_dir: Path | None = None) -> Path:
    dest = output_dir or _output_dir()
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "v1.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> dict:
    report = run_eval()
    path = write_report(report)
    print(json.dumps(report, indent=2))
    print(f"Wrote {path}")
    print(
        f"workflow_success_rate={report['workflow_success_rate']:.2f} "
        f"(threshold {WORKFLOW_SUCCESS_THRESHOLD:.2f})"
    )
    return report


if __name__ == "__main__":
    result = main()
    sys.exit(0 if result["workflow_success_rate"] >= WORKFLOW_SUCCESS_THRESHOLD else 1)
