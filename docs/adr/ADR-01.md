# ADR-01: Architecture style

**Status:** Accepted

**Options considered:** Microservices; modular monolith

**Decision:** Modular monolith: one FastAPI process serves API and UI

**Consequences:** One deploy for a 5-person, 12-week team; boundaries kept by package layout and review

**Revisit if:** A module needs to scale on its own
