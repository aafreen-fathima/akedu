# Architecture

Akedu is a layered modular monolith (ADR-01). A React single-page app calls a FastAPI backend, and the same process serves the built UI. Only the LLM gateway talks to a model; every date in the calendar and plan comes from deterministic code.

```
Browser (React)
   │  /api/v1  (session cookie, ownership check on every route)
FastAPI ──┬─ PDF intake ── temp file (deleted after job)
          ├─ Extraction job (background) ── LLM gateway ── Ollama | OpenAI-compatible | heuristic
          ├─ Crunch engine (pure, computed on read)
          ├─ Planner + validator + diff (pure)
          └─ ICS exporter
             │
          SQLite via SQLAlchemy (9 tables)
```

## Data model

User, Term, Course, UploadedDocument, ExtractionJob, Assessment, ReservedHours, Plan, PlanBlock.

- An assessment's `status` is either `extracted` or `confirmed`. Only confirmed rows reach the calendar, the crunch engine and the planner (R4).
- `due_time` is null for date-only deadlines; these are never coerced to midnight.
- `review_note` explains why a row is highlighted: a resolved "Week N" date, a missing weight, a date outside the term, or low confidence.
- Plans are versioned so R10 can compare the latest two.
- Crunch flags are computed on read and never stored (ADR-04).

## Upload and extraction flow

1. `POST /documents` validates the file type, size and text layer, stores a temp file, queues a job and returns `202`.
2. The background job extracts text per page (tables included) and calls `complete_json(prompt, schema)` once.
3. The reply is validated with Pydantic. An invalid reply is retried once, then the job is marked `needs_manual`.
4. Items are saved as `extracted`, "Week N" is resolved against the term (reading weeks skipped), and the temp PDF is deleted.
5. The UI polls `GET /documents` every 2 s while any job is queued or running.

## Algorithms

**Crunch.** A 7-day window starting at each confirmed due date is flagged when it holds 3 or more assessments or 30% or more summed weight. Overlapping flagged windows merge into one period, which lists its contributing assessments and the reason it was flagged.

**Planner.**
- A weekday is full when its reserved hours reach 8 h.
- Prep days = weight ÷ 5, clamped to between 1 and 7, with at least 3 for midterms and finals.
- Assessments are placed earliest deadline first, on the latest free days before the due date, with at most 2 blocks per day.
- Validation (R9): every assessment has a block before its due date, and no block lands on a full day. A plan that fails is regenerated once with the cap raised by 1. If no free day exists at all before a deadline, the plan reports it as a warning.
- Diff (R10): blocks are matched by assessment across the latest two plan versions.

See `adr/` for the decisions and their trade-offs.
