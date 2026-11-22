"""Rule-based extraction used by the `heuristic` provider (no LLM).

Reads the same prompt the LLM gets and returns the same JSON shape, so the
rest of the pipeline cannot tell the difference. It is deliberately simple:
it finds lines that name an assessment and carry a date, a week or a weight.
"""
from __future__ import annotations

import re

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
TYPE_WORDS = [
    ("final", r"\bfinal (exam|examination|test)\b"),
    ("midterm", r"\bmid-?term\b"),
    ("quiz", r"\bquiz(zes)?\b|\btest\b"),
    ("presentation", r"\bpresentation|\bpitch|\bdemo(nstration)?\b"),
    ("project", r"\bproject|\bmilestone|\bdeliverable|\breport\b|\bproposal\b|\bcase\s*stud"),
    ("lab", r"\blab\b"),
    ("assignment", r"\bassignment|\bhomework|\bjournal|\bLJ\d|\bexercise\b"),
]
ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
MONTH_DAY = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(20\d\d))?\b", re.I)
DAY_MONTH = re.compile(r"\b(\d{1,2})[-\s](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)[a-z]*\.?\b", re.I)
WEEK = re.compile(r"\bweek\s*(\d{1,2})\b", re.I)
WEIGHT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
TIME = re.compile(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", re.I)
COURSE = re.compile(r"\b([A-Z]{4})\s?-?(\d{3,4})\b")
YEAR_LINE = re.compile(r"TERM_YEAR:\s*(20\d\d)")
POLICY = re.compile(r"\blate\b|penalt|per day|will be (posted|submitted)|attendance", re.I)
PAGE = re.compile(r"^=== Page (\d+) ===$")


def _type_of(line: str) -> str | None:
    for kind, pat in TYPE_WORDS:
        if re.search(pat, line, re.I):
            return kind
    return None


def _date_of(line: str, year: int) -> str | None:
    if m := ISO.search(line):
        return m.group(0)
    if m := MONTH_DAY.search(line):
        mon = MONTHS[m.group(1).lower()[:4] if m.group(1).lower().startswith("sept") else m.group(1).lower()[:3]]
        return f"{int(m.group(3) or year):04d}-{mon:02d}-{int(m.group(2)):02d}"
    if m := DAY_MONTH.search(line):
        mon = MONTHS[m.group(2).lower()[:4] if m.group(2).lower().startswith("sept") else m.group(2).lower()[:3]]
        return f"{year:04d}-{mon:02d}-{int(m.group(1)):02d}"
    return None


def _clean_title(line: str) -> str:
    t = ISO.sub("", line)
    t = MONTH_DAY.sub("", t)
    t = DAY_MONTH.sub("", t)
    t = WEIGHT.sub("", t)
    t = TIME.sub("", t)
    t = re.sub(r"\(\s*\)|\|", " ", t)
    t = re.sub(r"\b(due|on|by|at|worth|weight)\b\s*[:]?", " ", t, flags=re.I)
    t = WEEK.sub("", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    t = re.sub(r"^[\s:,-]+", "", t).strip(" -–—:;,./()")
    return t[:80] or "Assessment"


def extract(prompt: str) -> dict:
    year_m = YEAR_LINE.search(prompt)
    year = int(year_m.group(1)) if year_m else 2026
    body = prompt.split("OUTLINE TEXT:", 1)[-1]
    code_m = COURSE.search(body)
    course_code = f"{code_m.group(1)} {code_m.group(2)}" if code_m else ""

    items, seen, page = [], set(), None
    for raw in body.splitlines():
        line = raw.strip()
        if pm := PAGE.match(line):
            page = int(pm.group(1))
            continue
        if not line or len(line) > 220:
            continue
        kind = _type_of(line)
        if not kind or POLICY.search(line):
            continue
        due = _date_of(line, year)
        week = WEEK.search(line)
        weight = WEIGHT.search(line)
        if not (due or week or weight):
            continue
        title = _clean_title(line)
        key = (title.lower(), due)
        if key in seen:
            continue
        seen.add(key)
        t = TIME.search(line)
        due_time = None
        if t and due:
            h = int(t.group(1)) % 12 + (12 if (t.group(3) or "").lower() == "pm" else 0) if t.group(3) else int(t.group(1))
            due_time = f"{h:02d}:{t.group(2)}"
        items.append({
            "title": title,
            "type": kind,
            "due_date": due,
            "due_time": due_time,
            "relative_week": int(week.group(1)) if week and not due else None,
            "weight_percent": float(weight.group(1)) if weight else None,
            "source_excerpt": line[:200],
            "source_page": page,
            "confidence": 0.6 if (due and weight) else 0.4,
        })

    expanded = []
    for item in items:
        title = item["title"]
        m = re.search(r"\(\s*(\d{1,2})\s*\)\s*$", title)
        m = m or re.search(r"\b(\d{1,2})\s+(assignments|case\s*studies|quizzes|projects|presentations|labs|reports|journals|exams)\b", title, re.I)
        if m and int(m.group(1)) > 1:
            count = int(m.group(1))
            base = re.sub(r"\s*\(\s*\d{1,2}\s*\)\s*$", "", title).strip()
            base = re.sub(r"\b\d{1,2}\s+(assignments|case\s*studies|quizzes|projects|presentations|labs|reports|journals|exams)\b", r"\1", base, flags=re.I)
            base = re.sub(r"\bCase\s+studies\b", "Case Study", base, flags=re.I)
            base = re.sub(r"\bAssignments\b", "Assignment", base, flags=re.I)
            for number in range(1, count + 1):
                copied = dict(item)
                copied["title"] = f"{base} #{number}"
                copied["weight_percent"] = round(item["weight_percent"] / count, 2) if item["weight_percent"] is not None else None
                copied["confidence"] = min(item["confidence"], 0.8)
                expanded.append(copied)
        else:
            expanded.append(item)
    return {"course_code": course_code, "course_title": "", "assessments": expanded}
