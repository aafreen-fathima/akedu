"""Date helpers: resolving "Week N" against the term calendar."""
from __future__ import annotations

from datetime import date, timedelta


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def in_break(d: date, breaks: list) -> bool:
    for start, end in breaks:
        if date.fromisoformat(start) <= d <= date.fromisoformat(end):
            return True
    return False


def resolve_week(week: int, term_start: date, breaks: list) -> date | None:
    """Monday of teaching week `week` (1-based), skipping break weeks."""
    if week < 1 or week > 30:
        return None
    d = monday_of(term_start)
    count = 0
    for _ in range(60):
        if not in_break(d, breaks):
            count += 1
            if count == week:
                return d
        d += timedelta(days=7)
    return None


def parse_breaks(spec: str) -> list[list[str]]:
    """"2026-10-12:2026-10-18,2026-12-01:2026-12-02" -> [[start, end], ...]."""
    out = []
    for part in filter(None, (p.strip() for p in spec.split(","))):
        start, _, end = part.partition(":")
        out.append([start, end or start])
    return out
