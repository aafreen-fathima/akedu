# Akedu — Syllabus-to-Workload Planner

SOEN 6841 Software Project Management · Concordia University · Fall 2026

Akedu turns a student's course outlines into one semester plan. Upload 3–5 PDF outlines, confirm the deadlines an LLM extracts, and see which weeks are crunch weeks across all your courses. You also get a day-range study plan that works around your job or TA hours and updates when your schedule changes.

## What it does

| Step | Screen | Requirement |
| --- | --- | --- |
| 1 | **Reserved hours**: weekly work/TA slots; a day with 8 h or more is a full day | R1 |
| 2 | **Upload**: PDF only, ≤ 10 MB, must have a text layer; extraction runs in the background | R2, R3 |
| 3 | **Review**: every extracted item shown beside its source text; uncertain items highlighted; nothing is used until confirmed | R3, R4 |
| 4 | **Calendar**: all courses in one month view, weight-per-week strip, explained crunch periods | R5, R6, R7 |
| 5 | **Study plan**: day-range blocks, never on full days, validated; re-plan shows what moved; `.ics` export | R8–R11 |

## Quick start

Requirements: Python 3.11+, Node 18+ (only to rebuild the UI).

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
AKEDU_LLM_PROVIDER=heuristic uvicorn app.main:app --port 8000
```

Open http://localhost:8000 and sign in with the pilot account **demo@akedu.app / akedu-demo**, or create an account. Sample outlines are in `samples/`.

The built UI is committed in `backend/app/static`, so no Node step is needed to run the app.

### Using a real LLM

Akedu talks to models only through `app/services/llm_gateway.py` (ADR-02). Pick a provider with environment variables (see `.env.example`):

| Provider | Settings | Notes |
| --- | --- | --- |
| `ollama` (default) | `AKEDU_LLM_MODEL=llama3.1:8b`, `AKEDU_LLM_BASE_URL=http://localhost:11434` | Local model; outlines never leave the machine. Run `ollama pull llama3.1:8b` first. |
| `openai` | `AKEDU_LLM_BASE_URL`, `AKEDU_LLM_MODEL`, `AKEDU_LLM_API_KEY` | Any OpenAI-compatible chat-completions API (hosted, LM Studio, vLLM). Tell students before upload (NF2). |
| `heuristic` | — | No model: a regex extractor with the same output shape. For offline demos, CI, and as the PoC baseline. |

Model replies are validated against a strict JSON schema. An invalid reply is retried once; if it fails again, the job is marked `needs_manual` and the student enters deadlines by hand.

### Frontend development

```bash
cd frontend && npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
npm run build      # writes to backend/app/static
```

### Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q
```

The suite (29 tests) covers the crunch rule (thresholds, day-7 boundary, merging), the planner (full days, per-day cap, validation, diff), PDF intake (non-PDF, size, scanned), Week-N date resolution, ICS format, ownership checks, and one end-to-end API run from reserved hours to export.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `AKEDU_LLM_PROVIDER` | `ollama` | `ollama`, `openai` or `heuristic` |
| `AKEDU_SECRET_KEY` | dev value | Session signing key; **set it** outside local dev |
| `AKEDU_TERM_START` / `_END` / `_BREAKS` | Fall 2026, reading week Oct 12–18 | Used to resolve "Week N" |
| `AKEDU_CRUNCH_MIN_COUNT` / `_MIN_WEIGHT` | 3 / 30 | Crunch thresholds (R6) |
| `AKEDU_FULL_DAY_HOURS` | 8 | Reserved hours that make a day full |
| `AKEDU_MAX_BLOCKS_PER_DAY` | 2 | Planner cap per day |
| `AKEDU_LLM_LABELS` | `false` | Let the LLM reword plan labels (dates never change) |
| `AKEDU_TODAY` | real date | Fix "today" for demos |

## Repository layout

```
backend/
  app/
    main.py            app, startup, static UI
    api.py             REST API (/api/v1)
    models.py          9 tables (SQLAlchemy, SQLite)
    services/
      pdf_intake.py    R2 validation + text extraction
      llm_gateway.py   ADR-02 provider adapter
      extraction.py    R3 job: prompt, schema, retry, Week-N, review notes
      crunch.py        R6 rule engine (pure)
      planner.py       R8–R10 scheduler, validator, diff (pure)
      ics.py           R11 export
  tests/
frontend/              React + Vite UI
docs/                  architecture, ADRs
samples/               fictional sample outlines
scripts/               sample-outline generator
AI_LOG.md              GenAI usage log (course requirement)
```

## Privacy (NF2)

- Every API route checks that the record belongs to the signed-in user, and returns 404 otherwise.
- Uploaded PDFs are deleted from disk as soon as extraction finishes. Only titles, dates, weights and short source excerpts are kept.
- Deleting an account cascades to all of the user's data.

## Team

