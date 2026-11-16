"""Generate fictional sample course outlines (PDF) for demos and tests.

Usage: python scripts/make_sample_outlines.py [output_dir]
The courses and dates are invented; they reproduce the Oct 20-23 crunch week
used in the design mockups.
"""
from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

OUTLINES = {
    "COMP6481_Outline_Sample.pdf": (
        "COMP 6481 Programming and Problem Solving",
        "This course covers problem solving, recursion, data structures and complexity. "
        "Lectures are on Wednesdays. Readings are posted on Moodle every week.",
        [["Assessment", "Weight", "Due"],
         ["Assignment 1", "8%", "Oct. 2"],
         ["Midterm exam", "25%", "October 20, in class"],
         ["Assignment 2", "12%", "Nov. 13"],
         ["Final exam", "40%", "Dec. 15"]],
        "Assignments are due at 23:59 on the date shown. Late work loses 10% per day.",
    ),
    "COMP6231_Outline_Sample.pdf": (
        "COMP 6231 Distributed System Design",
        "Topics: RPC, replication, consensus and fault tolerance. Team project in groups of four.",
        [["Deliverable", "Weight", "Date"],
         ["Project milestone 1", "10%", "Sep 25"],
         ["Project milestone 2", "15%", "Oct 22"],
         ["Quiz 2", "5%", "Oct 30"],
         ["Final project report", "30%", "Dec 4"]],
        "Week 10: project presentations (10%) during the lab session.",
    ),
    "COMP6721_Outline_Sample.pdf": (
        "COMP 6721 Applied Artificial Intelligence",
        "Search, knowledge representation, machine learning and evaluation.",
        [["Item", "Weight", "Deadline"],
         ["Quiz 1", "5%", "6-Oct"],
         ["Assignment 2", "10%", "23-Oct"],
         ["Final exam", "35%", "Dec. 18"]],
        "Lab attendance is recommended but not graded.",
    ),
}


def make(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    paths = []
    for name, (title, intro, table, note) in OUTLINES.items():
        path = out_dir / name
        doc = SimpleDocTemplate(str(path), pagesize=letter)
        doc.build([
            Paragraph(title, styles["Title"]),
            Paragraph("Fall 2026 · Sample outline (fictional, for testing Akedu)", styles["Normal"]),
            Spacer(1, 12),
            Paragraph(intro, styles["Normal"]),
            Spacer(1, 12),
            Paragraph("Evaluation", styles["Heading2"]),
            Table(table),
            Spacer(1, 12),
            Paragraph(note, styles["Normal"]),
        ])
        paths.append(path)
    return paths


if __name__ == "__main__":
    for p in make(Path(sys.argv[1] if len(sys.argv) > 1 else "samples")):
        print(p)
