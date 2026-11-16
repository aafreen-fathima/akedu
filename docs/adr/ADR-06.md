# ADR-06: Extraction runtime

**Status:** Accepted

**Options considered:** Synchronous request; FastAPI BackgroundTasks; RQ + Redis

**Decision:** BackgroundTasks plus an extraction_job table polled by the UI

**Consequences:** No extra infrastructure; jobs interrupted by a restart are marked failed at startup so the student can re-upload

**Revisit if:** More than a handful of concurrent users
