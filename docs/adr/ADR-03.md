# ADR-03: Planner

**Status:** Accepted

**Options considered:** LLM drafts + validator; deterministic; hybrid

**Decision:** Hybrid: deterministic scheduler places every date; LLM may only reword labels (AKEDU_LLM_LABELS)

**Consequences:** R9 holds by construction and plans are reproducible; labels are plainer without the LLM

**Revisit if:** Pilot plan ratings fall below the G3 target
