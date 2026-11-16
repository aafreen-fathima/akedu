"""Crunch engine (R6, R7, NF4, ADR-04). Pure function, computed on every read.

A 7-day window starting at each confirmed due date is flagged when it holds
>= min_count assessments or >= min_weight summed weight (across all courses).
Overlapping flagged windows merge into one crunch period.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class Item:
    id: int
    due: date
    weight: float | None


@dataclass
class CrunchPeriod:
    start: date
    end: date
    assessment_ids: list[int]
    count: int
    total_weight: float
    reasons: list[str] = field(default_factory=list)
    rule_version: str = "crunch-v1"


def detect(items: list[Item], window_days: int = 7, min_count: int = 3, min_weight: float = 30.0,
           rule_version: str = "crunch-v1") -> list[CrunchPeriod]:
    items = sorted((i for i in items if i.due is not None), key=lambda i: (i.due, i.id))
    flagged: list[tuple[date, date, list[Item]]] = []
    for anchor in items:
        s, e = anchor.due, anchor.due + timedelta(days=window_days - 1)
        inside = [i for i in items if s <= i.due <= e]
        weight = sum(i.weight or 0 for i in inside)
        if len(inside) >= min_count or weight >= min_weight:
            flagged.append((s, e, inside))

    periods: list[CrunchPeriod] = []
    cur_s = cur_e = None
    cur: dict[int, Item] = {}
    for s, e, inside in flagged:
        if cur_s is not None and s <= cur_e:
            cur_e = max(cur_e, e)
            cur.update({i.id: i for i in inside})
            continue
        if cur_s is not None:
            periods.append(_period(cur, min_count, min_weight, rule_version))
        cur_s, cur_e, cur = s, e, {i.id: i for i in inside}
    if cur_s is not None:
        periods.append(_period(cur, min_count, min_weight, rule_version))
    return periods


def _period(members: dict[int, Item], min_count: int, min_weight: float, rule_version: str) -> CrunchPeriod:
    its = sorted(members.values(), key=lambda i: (i.due, i.id))
    total = round(sum(i.weight or 0 for i in its), 2)
    reasons = []
    if len(its) >= min_count:
        reasons.append(f"{len(its)} assessments within 7 days (threshold {min_count})")
    if total >= min_weight:
        reasons.append(f"{total:g}% combined weight (threshold {min_weight:g}%)")
    return CrunchPeriod(start=its[0].due, end=its[-1].due, assessment_ids=[i.id for i in its],
                        count=len(its), total_weight=total, reasons=reasons, rule_version=rule_version)
