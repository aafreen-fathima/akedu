# AI usage log

The course requires this log. Record each significant use of generative AI: the date, tool, what was asked, what was used, and how the team checked it. Write the "Team check and decision" column yourselves.

| Date | Tool | What was asked | Output used | Team check and decision |
| --- | --- | --- | --- | --- |
| 2026-09-25 | Claude | Project setup: Drive folder, draft PID, storytelling pitch, repo scaffold | Draft PID and pitch structure | Used the draft as a starting point only. Wrote our own project content and dropped what did not fit the course guidelines. |
| 2026-09-27 | Claude | Format the final D1 (Project Initiation and Market Analysis), keep it to 4 pages | Formatting and typo fixes; content written by the team | Content was written by the team. Checked every AI-suggested competitor claim against the tools' own websites and kept the report within 4 pages. |
| 2026-11-06 / 07 | Claude | System architecture and design for D3: review of the team's draft, component diagram, data model, ADRs, traceability | Architecture doc, diagrams (PNG), ADR table | Compared the diagrams, data model and ADRs with R1 to R11 and NF1 to NF5. Kept the modular monolith and deterministic planner decisions. |
| 2026-11-07 | Claude (Claude Design) | UI screens for the five-step flow | Mockups for reserved hours, upload, review, calendar, plan | Checked each screen against the D3 wireframes and the requirement it covers. |
| 2026-11-15 | Claude | Implement the system end to end (instructor/TA approval for AI-assisted implementation confirmed by the team) | Backend (FastAPI), frontend (React), tests, docs in this repository | Reviewed the code against the requirements. All 29 automated tests and the CI run pass. Found three differences from D3 (rounding, retry method, crunch input) and a misleading "All checks passed" message shown next to an unscheduled assessment. Decision: fix the code to match D3. Real-model extraction is not benchmarked yet. |
