"""ICS exporter (R11): all-day VEVENTs for plan blocks and deadlines (RFC 5545)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    out, raw = [], line.encode("utf-8")
    while len(raw) > 75:
        cut = 75
        while (raw[cut] & 0xC0) == 0x80:  # don't split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = b" " + raw[cut:]
    out.append(raw.decode("utf-8"))
    return "\r\n".join(out)


def build_calendar(events: list[dict]) -> str:
    """events: {uid, summary, start: date, end: date (inclusive), description?}"""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Akedu//Semester Planner//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Akedu study plan"]
    for ev in events:
        start: date = ev["start"]
        end_excl: date = ev["end"] + timedelta(days=1)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev['uid']}@akedu",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
            f"DTEND;VALUE=DATE:{end_excl:%Y%m%d}",
            f"SUMMARY:{_esc(ev['summary'])}",
        ]
        if ev.get("description"):
            lines.append(f"DESCRIPTION:{_esc(ev['description'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
