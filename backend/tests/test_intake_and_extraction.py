import io
from datetime import date

import pytest
from reportlab.pdfgen import canvas

from app.services.dates import resolve_week
from app.services.ics import build_calendar
from app.services.pdf_intake import IntakeError, validate_pdf


def _blank_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(100, 100, 200, 200)  # a drawing, no text: like a scanned page
    c.save()
    return buf.getvalue()


def test_rejects_non_pdf():
    with pytest.raises(IntakeError) as e:
        validate_pdf("notes.docx", b"PK\x03\x04", 10)
    assert e.value.code == "not_pdf"


def test_rejects_large_file():
    with pytest.raises(IntakeError) as e:
        validate_pdf("big.pdf", b"%PDF" + b"0" * (2 * 1024 * 1024), 1)
    assert e.value.code == "file_too_large"


def test_rejects_scanned_pdf():
    with pytest.raises(IntakeError) as e:
        validate_pdf("scan.pdf", _blank_pdf(), 10)
    assert e.value.code == "no_text_layer"


def test_accepts_text_pdf(samples):
    path = samples["COMP6481_Outline_Sample.pdf"]
    info = validate_pdf(path.name, path.read_bytes(), 10)
    assert info.page_count == 1 and "Midterm" in info.pages[0]


def test_week_resolution_skips_reading_week():
    breaks = [["2026-10-12", "2026-10-18"]]
    start = date(2026, 9, 8)
    assert resolve_week(1, start, breaks) == date(2026, 9, 7)
    assert resolve_week(5, start, breaks) == date(2026, 10, 5)
    assert resolve_week(6, start, breaks) == date(2026, 10, 19)  # reading week skipped


def test_ics_is_rfc5545_shaped():
    text = build_calendar([{"uid": "x1", "summary": "Prepare, midterm; COMP 6481", "start": date(2026, 10, 16),
                            "end": date(2026, 10, 18)}])
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "DTSTART;VALUE=DATE:20261016" in text and "DTEND;VALUE=DATE:20261019" in text
    assert "SUMMARY:Prepare\\, midterm\\; COMP 6481" in text
