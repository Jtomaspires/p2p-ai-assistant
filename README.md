# P2P AI Assistant

Operator-facing HITL assistant for supplier payment-status emails. FastAPI + Celery + Postgres + Streamlit. Workflow nodes follow a Launchpad-style graph (`TicketWorkflow`), not a second orchestrator.

## Install

```bash
pip install -e ".[dev]"
```

Copy safe defaults (no real API keys):

```bash
copy .env.dev .env
```

On Unix: `cp .env.dev .env`. Set `LLM_PRIMARY_API_KEY` in `.env` only if you want live LLM calls.

## Infrastructure

```bash
docker compose up -d
alembic upgrade head
python scripts/generate_fixtures.py
```

## Run the stack (separate terminals on Windows)

PowerShell runs one blocking command at a time — do not chain `uvicorn` and `streamlit` in the same prompt.

```bash
uvicorn app.api.main:app --reload
```

```bash
celery -A app.workflow.tasks worker --pool=solo --loglevel=info
```

(`--pool=solo` is required on Windows.)

```bash
streamlit run app/dashboard/main.py
```

- API: http://localhost:8000
- Dashboard: http://localhost:8501

## Tests

```bash
pytest tests/ -v
```

## Eval and shadow (Fase 6–7)

Uses `TicketWorkflow(deps).run(...)` in-process (no Celery). Default LLM is a deterministic fixture-guided mock; live OpenAI-compatible models are used only when `LLM_PRIMARY_API_KEY` is set.

```bash
python scripts/run_eval.py
python scripts/run_shadow.py
```

Outputs:

- `golden_dataset/baselines/v1.json`
- `golden_dataset/baselines/shadow_v1.json`

Eval exits `1` if `workflow_success_rate` is below `0.80` (for CI). Set `EVAL_OUTPUT_DIR` to write elsewhere.

## Demo walkthrough (fixture 007)

1. `python scripts/generate_fixtures.py`
2. Ingest PAID-with-clearing:  
   `curl -X POST http://localhost:8000/webhook/mock -d @fixtures/emails/007_paid_with_clearing.json`
3. Confirm the Celery worker processed the task.
4. Open http://localhost:8501
5. Filter **HITL** — ticket should be `AWAITING_HUMAN`.
6. Select the ticket — draft to sender, payment-proof flag visible.
7. **Approve** — ticket moves to `RESOLVED` under **Todos** (use **Refresh** if needed).
8. Audit trail in Postgres: one `audit_entries` row per node class that ran.

## Layout

- `app/workflow/` — `TicketWorkflow` and nodes 0–8
- `app/api/` — webhook + dashboard HITL endpoints
- `app/dashboard/` — Streamlit operator UI
- `fixtures/` — golden emails + SAP mock
- `scripts/` — fixture generation, eval, shadow
