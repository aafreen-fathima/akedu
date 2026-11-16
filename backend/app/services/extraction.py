"""Extraction job (R3): outline text -> validated, unconfirmed assessments.

Runs in the background (ADR-06). Calls the LLM gateway once, validates the
reply against a strict schema, retries once on invalid output, and otherwise
marks the job `needs_manual`. The temporary PDF is deleted when the job ends.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Assessment, Course, ExtractionJob, Term, UploadedDocument
from .dates import resolve_week
from .llm_gateway import LLMError, LLMProvider
from .pdf_intake import extract_pages

log = logging.getLogger("akedu.extraction")
PROMPT_VERSION = "extract-v1"
TYPES = ["assignment", "quiz", "midterm", "final", "project", "presentation", "lab", "other"]
MAX_CHARS = 24000  # keeps a 7-8B local model inside its context window


class ExtractedItem(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    type: str = "other"
    due_date: date | None = None
    due_time: time | None = None
    relative_week: int | None = None
    weight_percent: float | None = Field(default=None, ge=0, le=100)
    source_excerpt: str = ""
    source_page: int | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)

    @field_validator("type", mode="before")
    @classmethod
    def _norm_type(cls, v):
        v = (v or "other").lower().strip()
        return v if v in TYPES else "other"


class Extraction(BaseModel):
    course_code: str = ""
    course_title: str = ""
    assessments: list[ExtractedItem]


SCHEMA = {
    "type": "object",
    "properties": {
        "course_code": {"type": "string"},
        "course_title": {"type": "string"},
        "assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "type": {"type": "string", "enum": TYPES},
                    "due_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                    "due_time": {"type": ["string", "null"], "description": "HH:MM, 24h"},
                    "relative_week": {"type": ["integer", "null"]},
                    "weight_percent": {"type": ["number", "null"]},
                    "source_excerpt": {"type": "string"},
                    "source_page": {"type": ["integer", "null"]},
                    "confidence": {"type": "number"},
                },
                "required": ["title", "type", "due_date", "weight_percent", "source_excerpt"],
            },
        },
    },
    "required": ["course_code", "course_title", "assessments"],
}

SYSTEM = (
    "You extract graded assessments from a university course outline. "
    "List every assignment, quiz, lab, project deliverable, presentation, midterm and final exam. "
    "Copy dates exactly as stated; never invent a date or a weight. "
    "If the outline gives only a teaching week (e.g. 'Week 7'), set due_date to null and relative_week to that number. "
    "If no weight is stated, set weight_percent to null. "
    "source_excerpt must quote the outline text the item came from, at most 200 characters. "
    "confidence is your certainty from 0 to 1. Ignore lecture topics and readings."
)


def build_prompt(pages: list[str], term: Term) -> str:
    text = "\n".join(f"=== Page {i} ===\n{p}" for i, p in enumerate(pages, start=1))
    return (
        f"TERM: {term.name}, {term.start_date.isoformat()} to {term.end_date.isoformat()}\n"
        f"TERM_YEAR: {term.start_date.year}\n"
        "Return the course code, course title and all graded assessments.\n\n"
        f"OUTLINE TEXT:\n{text[:MAX_CHARS]}"
    )


def _review_note(item: ExtractedItem, due: date | None, term: Term) -> str | None:
    notes = []
    if item.due_date is None and item.relative_week and due:
        notes.append(f"The outline says Week {item.relative_week}. We used Monday {due:%b %d}. Is that right?")
    elif due is None:
        notes.append("No due date found in the outline. Add one before confirming.")
    elif not (term.start_date <= due <= term.end_date):
        notes.append("This date falls outside the term. Check it against the outline.")
    if item.weight_percent is None:
        notes.append("No weight found in the outline. Add it, or leave it blank.")
    if item.confidence < 0.5 and not notes:
        notes.append("Low confidence. Compare with the source text.")
    return " ".join(notes) or None


def save_items(db: Session, job: ExtractionJob, doc: UploadedDocument, result: Extraction, term: Term) -> int:
    code = " ".join(result.course_code.upper().split()) or f"COURSE {doc.id}"
    course = db.scalar(select(Course).where(Course.user_id == doc.user_id, Course.term_id == term.id, Course.code == code))
    if course is None:
        course = Course(user_id=doc.user_id, term_id=term.id, code=code, title=result.course_title.strip())
        db.add(course)
        db.flush()
    elif result.course_title and not course.title:
        course.title = result.course_title.strip()
    doc.course_id = course.id
    for item in result.assessments:
        due = item.due_date or (resolve_week(item.relative_week, term.start_date, term.breaks) if item.relative_week else None)
        db.add(Assessment(
            course_id=course.id, job_id=job.id, title=item.title.strip(), type=item.type,
            due_date=due, due_time=item.due_time, weight_percent=item.weight_percent,
            source_excerpt=item.source_excerpt[:500], source_page=item.source_page,
            review_note=_review_note(item, due, term), status="extracted",
        ))
    return len(result.assessments)


def run_job(db: Session, job_id: int, provider: LLMProvider, settings: Settings) -> None:
    job = db.get(ExtractionJob, job_id)
    if job is None:
        return
    doc = job.document
    term = db.scalar(select(Term).order_by(Term.id))
    job.status, job.started_at = "running", datetime.now(timezone.utc)
    job.provider, job.model, job.prompt_version = provider.name, provider.model, PROMPT_VERSION
    db.commit()
    try:
        pages = extract_pages(Path(doc.storage_path).read_bytes())
        prompt = build_prompt(pages, term)
        result, last_error = None, ""
        for attempt in (1, 2):  # one retry on invalid output (R3)
            job.attempts = attempt
            try:
                reply = provider.complete_json(SYSTEM, prompt, SCHEMA)
                job.raw_output = reply.raw[:20000]
                result = Extraction.model_validate(reply.data)
                break
            except (LLMError, ValidationError) as exc:
                last_error = str(exc)[:2000]
                log.warning("job %s attempt %s failed: %s", job.id, attempt, last_error)
        if result is None:
            job.status, job.error = "needs_manual", last_error
        elif not result.assessments:
            job.status, job.error = "needs_manual", "No assessments were found in this outline."
        else:
            job.item_count = save_items(db, job, doc, result, term)
            job.status = "succeeded"
    except Exception as exc:  # never leave a job stuck in "running"
        log.exception("job %s crashed", job.id)
        db.rollback()
        job = db.get(ExtractionJob, job_id)
        job.status, job.error = "failed", str(exc)[:2000]
    finally:
        _delete_file(doc)
        job.finished_at = datetime.now(timezone.utc)
        db.commit()


def _delete_file(doc: UploadedDocument) -> None:
    """NF2: the PDF is removed from disk once extraction ends, success or not."""
    if doc.storage_path:
        Path(doc.storage_path).unlink(missing_ok=True)
        doc.storage_path = None
        doc.deleted_at = datetime.now(timezone.utc)
