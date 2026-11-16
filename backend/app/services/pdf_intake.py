"""PDF intake (R2): validate type, size and text layer; extract text per page."""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

import pdfplumber

MIN_TEXT_CHARS = 80


class IntakeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class PdfInfo:
    sha256: str
    page_count: int
    pages: list[str]


def validate_pdf(filename: str, data: bytes, max_mb: int) -> PdfInfo:
    if not filename.lower().endswith(".pdf") or not data.startswith(b"%PDF"):
        raise IntakeError("not_pdf", "Only PDF files are accepted.")
    if len(data) > max_mb * 1024 * 1024:
        raise IntakeError("file_too_large", f"This file is larger than {max_mb} MB.")
    try:
        pages = extract_pages(data)
    except Exception as exc:  # pdfplumber raises several types on corrupt files
        raise IntakeError("unreadable_pdf", "This PDF could not be opened. It may be damaged or password-protected.") from exc
    if sum(len(p.strip()) for p in pages) < MIN_TEXT_CHARS:
        raise IntakeError(
            "no_text_layer",
            "This looks like a scanned PDF: it has no selectable text, so Akedu can't read it. "
            "Upload a text-based PDF or enter the deadlines manually.",
        )
    return PdfInfo(sha256=hashlib.sha256(data).hexdigest(), page_count=len(pages), pages=pages)


def extract_pages(data: bytes) -> list[str]:
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            # tables often hold the deadlines; append them as pipe-separated rows
            for table in page.extract_tables() or []:
                rows = [" | ".join(c or "" for c in row) for row in table if row]
                if rows:
                    text += "\n" + "\n".join(rows)
            pages.append(text)
    return pages
