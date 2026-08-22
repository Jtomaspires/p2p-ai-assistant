"""Test Gate 2 — eval suite, LLM-as-judge, shadow rollout."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.adapters.mock_llm import MockLLMAdapter
from app.llm.judge import SCORING_KEYS, judge_draft
from scripts import run_eval, run_shadow


@pytest.fixture(scope="module")
def eval_output_dir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    dest = tmp_path_factory.mktemp("eval")
    previous = os.environ.get("EVAL_OUTPUT_DIR")
    os.environ["EVAL_OUTPUT_DIR"] = str(dest)
    yield dest
    if previous is None:
        os.environ.pop("EVAL_OUTPUT_DIR", None)
    else:
        os.environ["EVAL_OUTPUT_DIR"] = previous


@pytest.fixture(scope="module")
def eval_report(eval_output_dir: Path) -> dict:
    return run_eval.main()


@pytest.fixture(scope="module")
def shadow_report(eval_output_dir: Path) -> dict:
    return run_shadow.main()


def test_eval_main_writes_v1_json(eval_output_dir: Path, eval_report: dict) -> None:
    path = eval_output_dir / "v1.json"
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == eval_report


def test_v1_json_has_required_keys(eval_output_dir: Path, eval_report: dict) -> None:
    required = {
        "run_id",
        "workflow_success_rate",
        "intent_accuracy",
        "resolution_accuracy",
        "draft_target_accuracy",
        "draft_quality_avg",
        "failures",
        "notes",
    }
    assert required <= eval_report.keys()
    data = json.loads((eval_output_dir / "v1.json").read_text(encoding="utf-8"))
    assert required <= data.keys()


def test_eval_metric_ranges(eval_report: dict) -> None:
    for key in (
        "workflow_success_rate",
        "intent_accuracy",
        "resolution_accuracy",
        "draft_target_accuracy",
    ):
        assert isinstance(eval_report[key], float)
        assert 0.0 <= eval_report[key] <= 1.0
    avg = eval_report["draft_quality_avg"]
    assert isinstance(avg, float)
    assert avg == 0.0 or 1.0 <= avg <= 5.0


def test_eval_failures_is_list(eval_report: dict) -> None:
    assert isinstance(eval_report["failures"], list)


def test_v1_json_includes_model_and_run_id(eval_report: dict) -> None:
    assert eval_report["run_id"]
    assert "model" in eval_report
    assert isinstance(eval_report["model"], str)


def test_shadow_main_writes_shadow_v1(eval_output_dir: Path, shadow_report: dict) -> None:
    path = eval_output_dir / "shadow_v1.json"
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "n_emails",
        "intent_agreement",
        "routing_agreement",
        "draft_target_agreement",
        "escalation_agreement",
        "time_human_avg_s",
        "time_ai_avg_s",
    }
    assert required <= loaded.keys()
    assert required <= shadow_report.keys()
    assert loaded["n_emails"] == 20


def test_shadow_agreement_rates_in_unit_interval(shadow_report: dict) -> None:
    for key in (
        "intent_agreement",
        "routing_agreement",
        "draft_target_agreement",
        "escalation_agreement",
    ):
        assert 0.0 <= shadow_report[key] <= 1.0


@pytest.mark.asyncio
async def test_judge_draft_returns_scoring_keys() -> None:
    llm = MockLLMAdapter(
        [
            {
                "correctness": 5,
                "completeness": 4,
                "groundedness": 5,
                "tone": 4,
                "actionability": 3,
                "justification": "Grounded in ticket context.",
            }
        ]
    )
    result = await judge_draft("Please confirm INV-1 is paid.", {"invoice_ref": "INV-1"}, llm)
    for key in SCORING_KEYS:
        assert key in result
        assert result[key] in range(1, 6)
    assert "justification" in result
    assert set(SCORING_KEYS) | {"justification", "average"} == set(result.keys())


def test_run_eval_function_returns_report() -> None:
    report = run_eval.run_eval()
    assert "workflow_success_rate" in report
    assert isinstance(report["failures"], list)


def test_run_shadow_function_returns_report() -> None:
    report = run_shadow.run_shadow()
    assert report["n_emails"] == 20
    assert "intent_agreement" in report
