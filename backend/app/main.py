"""Akedu FastAPI application: API + built React app, one process (ADR-01)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from .api import router
from .auth import hash_password
from .config import settings
from .db import Base, SessionLocal, engine
from .models import ExtractionJob, Term, User
from .services.dates import parse_breaks

logging.basicConfig(level=logging.INFO)
STATIC = Path(__file__).parent / "static"


def init_db() -> None:
    if settings.database_url.startswith("sqlite:///"):
        Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(Term)) is None:
            db.add(Term(name=settings.term_name, start_date=date.fromisoformat(settings.term_start),
                        end_date=date.fromisoformat(settings.term_end), breaks=parse_breaks(settings.term_breaks)))
        # jobs lost on restart are marked failed so the student can re-upload (ADR-06)
        for job in db.scalars(select(ExtractionJob).where(ExtractionJob.status.in_(["queued", "running"]))):
            job.status, job.error = "failed", "The server restarted before this outline was read. Upload it again."
            job.finished_at = datetime.now(timezone.utc)
        if settings.seed_demo and db.scalar(select(User).where(User.email == "demo@akedu.app")) is None:
            db.add(User(email="demo@akedu.app", password_hash=hash_password("akedu-demo")))
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Akedu API", version="1.0.0", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax", max_age=60 * 60 * 24 * 14)
app.include_router(router)


@app.get("/api/health")
def health():
    return {"status": "ok", "llm_provider": settings.llm_provider, "model": settings.llm_model}


if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = STATIC / path
        if path and target.is_file() and STATIC in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(STATIC / "index.html")
