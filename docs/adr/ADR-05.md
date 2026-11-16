# ADR-05: Database

**Status:** Accepted

**Options considered:** SQLite; PostgreSQL

**Decision:** SQLite through SQLAlchemy

**Consequences:** Zero setup on the pilot machine; switching is a connection-string change

**Revisit if:** Concurrent writers or a hosted deployment
