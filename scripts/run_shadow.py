"""Simulated shadow rollout (Fase 7).

This shadow rollout is simulated with synthetic fixtures. The author plays both
roles (P2P operator baseline and system evaluator). Metrics replicate a real
shadow framework; they do not claim agreement with live customer operators.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval_harness import load_fixtures, run_fixture

DEFAULT_OUTPUT_DIR = ROOT / "golden_dataset" / "baselines"
HUMAN_TIME_S = 120.0

METHODOLOGY_NOTE = (
    "Simulated shadow rollout using synthetic fixtures, author as both "
    "human baseline and evaluator"
)


def _output_dir() -> Path:
    return Path(os.environ.get("EVAL_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))


def _human_routing_delegated(expected: dict) -> bool:
    return expected.get("ticket_status") == "delegated"


def _human_escalation(expected: dict) -> bool:
    return bool(expected.get("human_action_needed"))


def run_shadow() -> dict:
    fixtures = load_fixtures()
    n = len(fixtures)
    intent_hits = 0
    routing_hits = 0
    target_hits = 0
    escalation_hits = 0
    attach_hits = 0
    ai_times: list[float] = []
    rows: list[dict] = []

    for filename, fixture in fixtures:
        expected = fixture["expected"]
        started = time.perf_counter()
        _ctx, actual = run_fixture(fixture)
        elapsed = time.perf_counter() - started
        ai_times.append(elapsed)

        intent_ok = expected.get("intent") == actual.get("intent")
        routing_ok = _human_routing_delegated(expected) == actual.get("routing_delegated")
        target_ok = expected.get("draft_target") == actual.get("draft_target")
        esc_ok = _human_escalation(expected) == actual.get("human_action_needed")
        attach_ok = expected.get("attach_payment_proof") == actual.get("attach_payment_proof")

        intent_hits += int(intent_ok)
        routing_hits += int(routing_ok)
        target_hits += int(target_ok)
        escalation_hits += int(esc_ok)
        attach_hits += int(attach_ok)

        rows.append(
            {
                "id": fixture.get("id", filename),
                "intent_h": expected.get("intent"),
                "intent_ai": actual.get("intent"),
                "intent_match": intent_ok,
                "target_h": expected.get("draft_target"),
                "target_ai": actual.get("draft_target"),
                "target_match": target_ok,
                "time_ai_s": round(elapsed, 4),
            }
        )

    time_ai_avg = sum(ai_times) / n if n else 0.0
    report = {
        "shadow_run_id": f"{datetime.now(UTC).date().isoformat()}_v1",
        "n_emails": n,
        "intent_agreement": intent_hits / n if n else 0.0,
        "routing_agreement": routing_hits / n if n else 0.0,
        "draft_target_agreement": target_hits / n if n else 0.0,
        "escalation_agreement": escalation_hits / n if n else 0.0,
        "attachment_agreement": attach_hits / n if n else 0.0,
        "time_human_avg_s": HUMAN_TIME_S,
        "time_ai_avg_s": time_ai_avg,
        "speedup_factor": (HUMAN_TIME_S / time_ai_avg) if time_ai_avg else 0.0,
        "notes": METHODOLOGY_NOTE,
        "cases": rows,
    }
    return report


def write_report(report: dict, output_dir: Path | None = None) -> Path:
    dest = output_dir or _output_dir()
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "shadow_v1.json"
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def main() -> dict:
    report = run_shadow()
    path = write_report(report)
    print(METHODOLOGY_NOTE)
    print(f"{'id':<22} {'intent H/AI':<28} {'target H/AI':<28} match")
    for row in report["cases"]:
        print(
            f"{row['id']:<22} {row['intent_h']!s}/{row['intent_ai']!s:<16} "
            f"{row['target_h']!s}/{row['target_ai']!s:<16} "
            f"{'Y' if row['intent_match'] and row['target_match'] else 'N'}"
        )
    summary = {k: report[k] for k in report if k != "cases"}
    print(json.dumps(summary, indent=2))
    print(f"Wrote {path}")
    return report


if __name__ == "__main__":
    main()
    sys.exit(0)
