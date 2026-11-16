"""Planner (R8, R9, R10, ADR-03). Pure functions; dates come only from here.

1. Availability: a weekday whose reserved hours reach `full_day_hours` is a full day.
2. Placement: earliest deadline first (heavier first on ties); prep days go on the
   latest free days before the due date, at most `max_per_day` blocks per day.
3. Validation (R9): each assessment has a block ending before its due date; no
   block covers a full day; every block lies between today and term end.
4. Diff (R10): blocks matched by assessment across two plan versions.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time, timedelta

EXAM_TYPES = {"midterm", "final"}


@dataclass(frozen=True)
class Task:
    id: int
    course_code: str
    title: str
    type: str
    due: date
    weight: float | None


@dataclass(frozen=True)
class Slot:
    weekday: int
    start: time
    end: time


@dataclass
class Block:
    assessment_id: int
    label: str
    start: date
    end: date


@dataclass
class PlanResult:
    blocks: list[Block]
    is_valid: bool
    errors: list[str]
    warnings: list[str]


def full_weekdays(slots: list[Slot], full_day_hours: float) -> set[int]:
    hours: dict[int, float] = defaultdict(float)
    for s in slots:
        minutes = (s.end.hour * 60 + s.end.minute) - (s.start.hour * 60 + s.start.minute)
        hours[s.weekday] += max(0, minutes) / 60
    return {d for d, h in hours.items() if h >= full_day_hours}


def prep_days(task: Task) -> int:
    n = max(1, min(7, round((task.weight or 0) / 5)))
    return max(n, 3) if task.type in EXAM_TYPES else n


def label_for(task: Task) -> str:
    verb = "Prepare for" if task.type in EXAM_TYPES or task.type == "quiz" else "Work on"
    return f"{verb} {task.title} ({task.course_code})"


def _place(tasks: list[Task], full: set[int], today: date, term_end: date, cap: int) -> list[Block]:
    load: dict[date, int] = defaultdict(int)
    blocks: list[Block] = []
    for t in sorted(tasks, key=lambda t: (t.due, -(t.weight or 0), t.id)):
        need, chosen = prep_days(t), []
        d = min(t.due - timedelta(days=1), term_end)
        while d >= today and len(chosen) < need:
            if d.weekday() not in full and load[d] < cap:
                chosen.append(d)
            d -= timedelta(days=1)
        for day in chosen:
            load[day] += 1
        blocks.extend(_runs(t, sorted(chosen)))
    return blocks


def _runs(task: Task, days: list[date]) -> list[Block]:
    """Group consecutive chosen days into day-range blocks."""
    out: list[Block] = []
    for d in days:
        if out and out[-1].end + timedelta(days=1) == d:
            out[-1].end = d
        else:
            out.append(Block(task.id, label_for(task), d, d))
    return out


def _has_free_day(task: Task, full: set[int], today: date) -> bool:
    d = task.due - timedelta(days=1)
    while d >= today:
        if d.weekday() not in full:
            return True
        d -= timedelta(days=1)
    return False


def validate(blocks: list[Block], tasks: list[Task], full: set[int], today: date, term_end: date) -> list[str]:
    """R9 checks. Tasks with no free day at all before their due date are not the
    planner's failure; they are reported separately as warnings by generate()."""
    errors = []
    by_task = defaultdict(list)
    for b in blocks:
        by_task[b.assessment_id].append(b)
        d = b.start
        while d <= b.end:
            if d.weekday() in full:
                errors.append(f"'{b.label}' covers a full day ({d:%a %b %d}).")
                break
            d += timedelta(days=1)
        if b.start < today or b.end > term_end:
            errors.append(f"'{b.label}' falls outside today–term end.")
    for t in tasks:
        if _has_free_day(t, full, today) and not any(b.end < t.due for b in by_task[t.id]):
            errors.append(f"No free day left to prepare for {t.title} ({t.course_code}), due {t.due:%a %b %d}.")
    return errors


def generate(tasks: list[Task], slots: list[Slot], today: date, term_end: date,
             full_day_hours: float = 8, max_per_day: int = 2) -> PlanResult:
    tasks = [t for t in tasks if t.due > today]
    full = full_weekdays(slots, full_day_hours)
    blocks = _place(tasks, full, today, term_end, max_per_day)
    errors = validate(blocks, tasks, full, today, term_end)
    if errors:  # regenerate once with the per-day cap raised by 1
        blocks = _place(tasks, full, today, term_end, max_per_day + 1)
        errors = validate(blocks, tasks, full, today, term_end)
    warnings = [f"No free day is left before {t.title} ({t.course_code}), due {t.due:%a %b %d}."
                for t in tasks if not _has_free_day(t, full, today)]
    blocks.sort(key=lambda b: (b.start, b.assessment_id))
    return PlanResult(blocks=blocks, is_valid=not errors, errors=errors, warnings=warnings)


def diff(old: list[Block], new: list[Block]) -> dict[str, list[dict]]:
    def ranges(bs):
        out = defaultdict(list)
        for b in bs:
            out[b.assessment_id].append((b.start, b.end))
        return {k: sorted(v) for k, v in out.items()}

    def fmt(rs):
        return [{"start": s.isoformat(), "end": e.isoformat()} for s, e in rs]

    o, n = ranges(old), ranges(new)
    label = {b.assessment_id: b.label for b in [*old, *new]}
    result = {"added": [], "removed": [], "moved": [], "unchanged": []}
    for aid in sorted(set(o) | set(n)):
        entry = {"assessment_id": aid, "label": label[aid]}
        if aid not in o:
            result["added"].append({**entry, "now": fmt(n[aid])})
        elif aid not in n:
            result["removed"].append({**entry, "was": fmt(o[aid])})
        elif o[aid] != n[aid]:
            result["moved"].append({**entry, "was": fmt(o[aid]), "now": fmt(n[aid])})
        else:
            result["unchanged"].append({**entry, "now": fmt(n[aid])})
    return result
