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
PROMPT_VERSION = "extract-v2"
TYPES = ["assignment", "quiz", "midterm", "final", "project", "presentation", "lab", "other"]
MAX_CHARS = 64000


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

    @field_validator("due_date", mode="before")
    @classmethod
    def _norm_due_date(cls, v, info):
        if v is None or isinstance(v, (date, datetime)):
            return v
        if not isinstance(v, str):
            return v

        value = v.strip()
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass

        year = (info.context or {}).get("year", 2026)
        m = _re.fullmatch(r"(\d{1,2})[-\s](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?", value, _re.I)
        if m:
            mon_key = m.group(2).lower()
            mon = _MONTHS.get("sept" if mon_key == "sept" else mon_key[:3])
            if mon:
                return date(int(year), mon, int(m.group(1)))

        m = _re.fullmatch(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:,\s*(20\d\d))?", value, _re.I)
        if m:
            mon_key = m.group(1).lower()
            mon = _MONTHS.get("sept" if mon_key == "sept" else mon_key[:3])
            if mon:
                resolved_year = int(m.group(3)) if m.group(3) else int(year)
                return date(resolved_year, mon, int(m.group(2)))
        return value

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
    "You are an expert at reading university course outlines and extracting graded assessments.\n\n"

    "PRIMARY SOURCE — GRADING SCHEME:\n"
    "1. First extract every row from the assessment/grading table. The table is authoritative for item names and weights.\n"
    "2. Split a repeated row into separate assessments whenever the name/count indicates a series: "
    "'Assignments (4)' means Assignment #1 through Assignment #4, and 'Case studies (3)' means Case Study #1 through "
    "Case Study #3. Divide the row weight equally unless the outline gives individual weights.\n"
    "3. Do not combine separate numbered items. Do not combine two groups merely because they are on the same page.\n"
    "4. Include projects, reports, presentations, labs, quizzes, tests, midterms, finals, learning journals, "
    "participation components, case studies, and any other explicitly graded item.\n\n"

    "SECONDARY SOURCE — WEEKLY/TENTATIVE SCHEDULE:\n"
    "1. Use the schedule only after the grading table to add exact due dates or relative week numbers.\n"
    "2. Match the assessment title and number to the schedule (Assignment #1 with Week 3, Exam 1 with its dated row).\n"
    "3. Prefer an exact date in the schedule. Otherwise set due_date to null and relative_week to the schedule week.\n"
    "4. A schedule mention does not create a new assessment that is absent from the grading scheme.\n\n"

    "WHAT TO IGNORE:\n"
    "- Lecture topics, readings, and weekly content descriptions.\n"
    "- Columns about GenAI levels, GenAI permitted use, or disclosure requirements — these are not assessments.\n"
    "- Policy text (late penalties, attendance, plagiarism).\n"
    "- Duplicate rows (the same assessment appearing twice in the outline).\n\n"

    "DATE RULES — follow these exactly:\n"
    "1. due_date MUST be in YYYY-MM-DD format, or null. No other format is accepted.\n"
    "2. Use the TERM_YEAR from the prompt to supply the year for partial dates.\n"
    "   Examples: 'Oct. 26' with TERM_YEAR 2026 → '2026-10-26'; '02-Nov' → '2026-11-02'; 'Dec. 7' → '2026-12-07'.\n"
    "3. Dates often appear in a schedule table alongside week numbers and lecture topics. "
    "   Look for rows like '6  26-Oct  Exam 1 (Oct. 26)' — the date is there, not in the grading table.\n"
    "4. If the outline only says a week number (e.g. 'Week 6' or 'Week #6'), set due_date to null "
    "   and relative_week to that integer.\n"
    "5. If a single assessment has multiple due dates (e.g. tests on Nov. 8, Nov. 22, Nov. 30), "
    "   create one separate assessment entry per date.\n"
    "6. If no date is found anywhere for an item, set due_date to null.\n\n"

    "WEIGHT RULES:\n"
    "- Use the percentage from the grading scheme table.\n"
    "- If the outline says '4%' for 'Assignments (4)', each individual assignment is 1% (4% / 4). "
    "  Create one entry per assignment with weight 1.0, not one entry with 4%.\n"
    "- If no weight is stated, set weight_percent to null. Never invent a weight.\n\n"

    "OUTPUT RULES:\n"
    "- source_excerpt: quote the exact text from the outline the item came from (max 200 characters).\n"
    "- confidence: your certainty 0.0–1.0. Use 0.9 when date+weight are explicit, 0.6 when inferred.\n"
    "- course_code: use the standard format, e.g. 'SOEN 6841'. If not found, leave empty."
)


import re as _re

# Matches schedule rows like:  "6  26-Oct  Exam 1 (Oct. 26)  LJ2"
# or                            "2  21-Sep  LJ1 (Sep. 27)"
_SCHED_ROW = _re.compile(
    r"^\s*(\d{1,2})\s+(\d{1,2})[-\s](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\b",
    _re.IGNORECASE | _re.MULTILINE,
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _week_date_map(text: str, year: int) -> dict[int, str]:
    """Scan outline text for schedule-table rows and return {week_num: 'YYYY-MM-DD'}."""
    mapping: dict[int, str] = {}
    for m in _SCHED_ROW.finditer(text):
        week = int(m.group(1))
        day = int(m.group(2))
        mon_key = m.group(3).lower()[:4]  # handles "sept" vs "sep"
        mon = _MONTHS.get(mon_key) or _MONTHS.get(mon_key[:3])
        if mon and 1 <= week <= 20:
            mapping[week] = f"{year}-{mon:02d}-{day:02d}"
    return mapping


def _associate_with_schedule(
    item: ExtractedItem,
    schedule_rows: list[tuple[int | None, date | None, str]],
    week_dates: dict[int, str],
    term: Term,
) -> ExtractedItem:
    if item.due_date is not None:
        return item

    title = item.title.lower()
    number_match = _re.search(r"(?:#\s*|(?:exam|test|assignment|case\s*study|project|quiz)\s*)(\d{1,2})\b", title, _re.I)
    number = int(number_match.group(1)) if number_match else None
    base = _re.sub(r"\s*#?\s*\d{1,2}\s*$", "", title).strip(" :-")

    for row_week, row_date, line in schedule_rows:
        lower_line = line.lower()
        title_match = base in lower_line or (
            base.endswith(" assignment") and "assignment" in lower_line
        )
        if not title_match:
            continue
        if number is not None:
            number_in_line = _re.search(rf"(?:#\s*|(?:exam|test|assignment|case\s*study|project|quiz)\s*){number}\b", lower_line, _re.I)
            if not number_in_line:
                continue

        explicit = _re.search(
            r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:,\s*(20\d\d))?\b",
            line,
            _re.I,
        )
        if explicit:
            mon_key = explicit.group(1).lower()
            mon = _MONTHS.get("sept" if mon_key == "sept" else mon_key[:3])
            if mon:
                try:
                    resolved_year = int(explicit.group(3)) if explicit.group(3) else term.start_date.year
                    return item.model_copy(update={
                        "due_date": date(resolved_year, mon, int(explicit.group(2))),
                        "relative_week": row_week,
                    })
                except ValueError:
                    pass
        if row_date:
            return item.model_copy(update={"due_date": row_date, "relative_week": row_week})
        if row_week:
            return item.model_copy(update={"relative_week": row_week})

    if item.relative_week is not None:
        week_date = week_dates.get(item.relative_week)
        if week_date:
            item = item.model_copy(update={"due_date": date.fromisoformat(week_date)})
    return item


def build_prompt(pages: list[str], term: Term) -> str:
    full_text = "\n".join(f"=== Page {i} ===\n{p}" for i, p in enumerate(pages, start=1))
    year = term.start_date.year

    # Build an explicit week→date map from the schedule table and inject it
    week_map = _week_date_map(full_text, year)
    if week_map:
        sorted_weeks = sorted(week_map.items())
        week_hint = "WEEK_SCHEDULE (use these exact dates for each teaching week):\n"
        week_hint += "\n".join(f"  Week {w} starts on {d}" for w, d in sorted_weeks)
        week_hint += "\n"
    else:
        week_hint = ""

    return (
        f"TERM: {term.name}, {term.start_date.isoformat()} to {term.end_date.isoformat()}\n"
        f"TERM_YEAR: {year}\n"
        f"{week_hint}"
        "TASK: Extract the course code, course title, and all graded assessments from the outline below.\n"
        "HINT: Cross-reference the grading scheme (which has weights) with the WEEK_SCHEDULE above "
        "and the schedule table in the text (which has due dates). Use the WEEK_SCHEDULE dates when "
        "an assessment is listed in a specific week row. Convert all dates to YYYY-MM-DD.\n\n"
        f"OUTLINE TEXT:\n{full_text[:MAX_CHARS]}"
    )


def normalize_assessments(result: Extraction, pages: list[str], term: Term) -> Extraction:
    """Expand grouped grading rows and correlate them with the schedule."""
    text = "\n".join(pages)
    week_dates = _week_date_map(text, term.start_date.year)
    schedule_rows: list[tuple[int | None, date | None, str]] = []

    for line in text.splitlines():
        week_m = _re.search(r"\bWeek\s*#?(\d{1,2})\b", line, _re.I)
        leading_m = _re.match(r"\s*(\d{1,2})\s+(?:\d{1,2}[-]\w{3}|\d{1,2}\s+[A-Za-z]{3})", line)
        schedule_m = _re.search(r"\b(?:\d{1,2})[-\s](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\b", line, _re.I)
        row_week = int(week_m.group(1)) if week_m else (int(leading_m.group(1)) if leading_m else None)
        row_date = None
        if schedule_m:
            day_m = _re.search(r"\b(\d{1,2})[-\s]", schedule_m.group(0))
            mon_key = schedule_m.group(1).lower()
            mon = _MONTHS.get(mon_key[:4] if mon_key.startswith("sept") else mon_key[:3])
            if day_m and mon:
                try:
                    row_date = date(term.start_date.year, mon, int(day_m.group(1)))
                except ValueError:
                    row_date = None
        schedule_rows.append((row_week, row_date, line))

    normalized: list[ExtractedItem] = []
    for item in result.assessments:
        title = item.title.strip()
        count_m = (
            _re.search(r"\(\s*(\d{1,2})\s*\)\s*$", title)
            or _re.search(r"\b(\d{1,2})\s+(assignments|case\s*studies|quizzes|projects|presentations|labs|reports|journals|exams)\b", title, _re.I)
        )
        if count_m:
            count = int(count_m.group(1))
            base_title = _re.sub(r"\s*\(\s*\d{1,2}\s*\)\s*$", "", title).strip()
            base_title = _re.sub(r"\b\d{1,2}\s+(assignments|case\s*studies|quizzes|projects|presentations|labs|reports|journals|exams)\b", r"\1", base_title, flags=_re.I).strip()
            matching = [
                other for other in result.assessments
                if other is not item
                and base_title.lower() in other.title.lower()
                and _re.search(r"#?\s*\d+", other.title)
            ]
            if count > 1 and len(matching) < count:
                for number in range(1, count + 1):
                    singular_title = base_title
                    singular_title = _re.sub(r"\bCase\s+studies\b", "Case Study", singular_title, flags=_re.I)
                    singular_title = _re.sub(r"\bAssignments\b", "Assignment", singular_title, flags=_re.I)
                    singular_title = _re.sub(r"\bQuizzes\b", "Quiz", singular_title, flags=_re.I)
                    singular_title = _re.sub(r"\bProjects\b", "Project", singular_title, flags=_re.I)
                    singular_title = _re.sub(r"\bPresentations\b", "Presentation", singular_title, flags=_re.I)
                    singular_title = _re.sub(r"\bLabs\b", "Lab", singular_title, flags=_re.I)
                    singular_title = _re.sub(r"\bReports\b", "Report", singular_title, flags=_re.I)
                    singular_title = _re.sub(r"\bJournals\b", "Journal", singular_title, flags=_re.I)
                    singular_title = _re.sub(r"\bExams\b", "Exam", singular_title, flags=_re.I)
                    individual_title = f"{singular_title} #{number}"
                    individual = item.model_copy(update={
                        "title": individual_title,
                        "weight_percent": round(item.weight_percent / count, 2) if item.weight_percent is not None else None,
                        "confidence": min(item.confidence, 0.8),
                    })
                    individual = _associate_with_schedule(individual, schedule_rows, week_dates, term)
                    normalized.append(individual)
                continue

        normalized.append(_associate_with_schedule(item, schedule_rows, week_dates, term))

    return result.model_copy(update={"assessments": normalized})


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
                result = Extraction.model_validate(reply.data, context={"year": term.start_date.year})
                result = normalize_assessments(result, pages, term)
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
