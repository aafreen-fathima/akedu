"""REST API under /api/v1. Every route except auth checks ownership (NF2)."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import schemas as s
from .auth import current_user, hash_password, not_found, verify_password
from .config import settings
from .db import SessionLocal, get_db
from .models import Assessment, Course, ExtractionJob, Plan, PlanBlock, ReservedHours, Term, UploadedDocument, User
from .services import crunch, planner
from .services.extraction import run_job
from .services.ics import build_calendar
from .services.llm_gateway import get_provider
from .services.pdf_intake import IntakeError, validate_pdf

router = APIRouter(prefix="/api/v1")


def err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def term_of(db: Session) -> Term:
    return db.scalar(select(Term).order_by(Term.id))


# ---------- auth ----------
@router.post("/auth/register", response_model=s.UserOut)
def register(body: s.Credentials, request: Request, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise err(409, "email_taken", "An account with this email already exists.")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    request.session["uid"] = user.id
    return user


@router.post("/auth/login", response_model=s.UserOut)
def login(body: s.Credentials, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise err(401, "bad_credentials", "Email or password is incorrect.")
    request.session["uid"] = user.id
    return user


@router.post("/auth/logout", status_code=204)
def logout(request: Request):
    request.session.clear()
    return Response(status_code=204)


@router.get("/auth/me", response_model=s.UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.delete("/account", status_code=204)
def delete_account(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """NF2: deleting the account cascades to everything the user owns."""
    db.delete(user)
    db.commit()
    request.session.clear()
    return Response(status_code=204)


@router.get("/term", response_model=s.TermOut)
def term(db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = term_of(db)
    return s.TermOut(name=t.name, start_date=t.start_date, end_date=t.end_date, breaks=t.breaks, today=settings.today())


# ---------- reserved hours (R1) ----------
@router.get("/reserved-hours", response_model=list[s.SlotOut])
def get_hours(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(ReservedHours).where(ReservedHours.user_id == user.id)
                      .order_by(ReservedHours.weekday, ReservedHours.start_time)).all()


@router.put("/reserved-hours", response_model=list[s.SlotOut])
def put_hours(body: list[s.SlotIn], user: User = Depends(current_user), db: Session = Depends(get_db)):
    for slot in body:
        if slot.end_time <= slot.start_time:
            raise err(422, "bad_slot", "Each slot must end after it starts.")
    by_day: dict[int, list[s.SlotIn]] = {}
    for slot in body:
        for other in by_day.get(slot.weekday, []):
            if slot.start_time < other.end_time and other.start_time < slot.end_time:
                raise err(422, "overlap", "Two slots on the same day overlap.")
        by_day.setdefault(slot.weekday, []).append(slot)
    for old in db.scalars(select(ReservedHours).where(ReservedHours.user_id == user.id)):
        db.delete(old)
    for slot in body:
        db.add(ReservedHours(user_id=user.id, **slot.model_dump()))
    db.commit()
    return get_hours(user, db)


# ---------- documents and jobs (R2, R3) ----------
def _job_runner(job_id: int) -> None:
    db = SessionLocal()
    try:
        run_job(db, job_id, get_provider(settings), settings)
    finally:
        db.close()


def _doc_out(doc: UploadedDocument, db: Session) -> s.DocumentOut:
    job = max(doc.jobs, key=lambda j: j.id) if doc.jobs else None
    course = db.get(Course, doc.course_id) if doc.course_id else None
    return s.DocumentOut(id=doc.id, filename=doc.filename, page_count=doc.page_count,
                         course_code=course.code if course else None, uploaded_at=doc.uploaded_at,
                         job=s.JobOut.model_validate(job) if job else None)


@router.post("/documents", response_model=s.DocumentOut, status_code=202)
async def upload(background: BackgroundTasks, file: UploadFile = File(...),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = await file.read()
    try:
        info = validate_pdf(file.filename or "", data, settings.max_upload_mb)
    except IntakeError as e:
        raise err(400, e.code, e.message)
    active = db.scalars(select(UploadedDocument).where(UploadedDocument.user_id == user.id)).all()
    if len(active) >= 8:
        raise err(400, "too_many_files", "You can keep up to 8 outlines. Remove one first.")
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    path = settings.upload_dir / f"{uuid.uuid4().hex}.pdf"
    path.write_bytes(data)
    doc = UploadedDocument(user_id=user.id, filename=(file.filename or "outline.pdf")[:255], sha256=info.sha256,
                           page_count=info.page_count, storage_path=str(path))
    db.add(doc)
    db.flush()
    job = ExtractionJob(document_id=doc.id, status="queued")
    db.add(job)
    db.commit()
    background.add_task(_job_runner, job.id)
    db.refresh(doc)
    return _doc_out(doc, db)


@router.get("/documents", response_model=list[s.DocumentOut])
def list_documents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    docs = db.scalars(select(UploadedDocument).where(UploadedDocument.user_id == user.id)
                      .order_by(UploadedDocument.id)).all()
    return [_doc_out(d, db) for d in docs]


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Removes the document and the unconfirmed items it produced; confirmed items stay."""
    doc = db.get(UploadedDocument, doc_id)
    if doc is None or doc.user_id != user.id:
        raise not_found()
    job_ids = [j.id for j in doc.jobs]
    if job_ids:
        for a in db.scalars(select(Assessment).where(Assessment.job_id.in_(job_ids), Assessment.status == "extracted")):
            db.delete(a)
    if doc.storage_path:
        from pathlib import Path
        Path(doc.storage_path).unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
    return Response(status_code=204)


@router.get("/jobs/{job_id}", response_model=s.JobOut)
def get_job(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(ExtractionJob, job_id)
    if job is None or job.document.user_id != user.id:
        raise not_found()
    return job


# ---------- courses and assessments (R3, R4, R7) ----------
def _a_out(a: Assessment) -> s.AssessmentOut:
    return s.AssessmentOut(id=a.id, course_id=a.course_id, course_code=a.course.code, title=a.title, type=a.type,
                           due_date=a.due_date, due_time=a.due_time, weight_percent=a.weight_percent,
                           source_excerpt=a.source_excerpt, source_page=a.source_page,
                           review_note=a.review_note, status=a.status)


def _owned_assessment(aid: int, user: User, db: Session) -> Assessment:
    a = db.get(Assessment, aid)
    if a is None or a.course.user_id != user.id:
        raise not_found()
    return a


def _user_assessments(user: User, db: Session, status: str | None = None) -> list[Assessment]:
    q = select(Assessment).join(Course).where(Course.user_id == user.id)
    if status:
        q = q.where(Assessment.status == status)
    return db.scalars(q.order_by(Assessment.due_date.is_(None), Assessment.due_date, Assessment.id)).all()


@router.get("/courses", response_model=list[s.CourseOut])
def courses(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Course).where(Course.user_id == user.id).order_by(Course.code)).all()


@router.get("/assessments", response_model=list[s.AssessmentOut])
def list_assessments(status: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_a_out(a) for a in _user_assessments(user, db, status)]


@router.post("/assessments", response_model=s.AssessmentOut, status_code=201)
def add_assessment(body: s.AssessmentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Manual entry (R7, and the fallback when extraction fails). Confirmed on creation."""
    t = term_of(db)
    code = " ".join(body.course_code.upper().split())
    course = db.scalar(select(Course).where(Course.user_id == user.id, Course.term_id == t.id, Course.code == code))
    if course is None:
        course = Course(user_id=user.id, term_id=t.id, code=code)
        db.add(course)
        db.flush()
    a = Assessment(course_id=course.id, title=body.title.strip(), type=body.type, due_date=body.due_date,
                   due_time=body.due_time, weight_percent=body.weight_percent,
                   source_excerpt="Entered manually", status="confirmed")
    db.add(a)
    db.commit()
    db.refresh(a)
    return _a_out(a)


@router.patch("/assessments/{aid}", response_model=s.AssessmentOut)
def patch_assessment(aid: int, body: s.AssessmentPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _owned_assessment(aid, user, db)
    fields = body.model_dump(exclude_unset=True)
    for k, v in fields.items():
        setattr(a, k, v)
    if fields.keys() - {"status"}:
        a.review_note = None  # the student has looked at it
    if a.status == "confirmed" and a.due_date is None:
        raise err(422, "missing_due_date", "Add a due date before confirming.")
    db.commit()
    db.refresh(a)
    return _a_out(a)


@router.post("/assessments/confirm", response_model=list[s.AssessmentOut])
def confirm(body: s.ConfirmIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = []
    for aid in body.ids:
        a = _owned_assessment(aid, user, db)
        if a.due_date is None:
            raise err(422, "missing_due_date", f"'{a.title}' has no due date yet.")
        a.status = "confirmed"
        out.append(a)
    db.commit()
    return [_a_out(a) for a in out]


@router.delete("/assessments/{aid}", status_code=204)
def delete_assessment(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_owned_assessment(aid, user, db))
    db.commit()
    return Response(status_code=204)


# ---------- calendar and crunch (R5, R6, R7) ----------
def _crunch(user: User, db: Session) -> list[crunch.CrunchPeriod]:
    items = [crunch.Item(a.id, a.due_date, a.weight_percent) for a in _user_assessments(user, db, "confirmed")]
    return crunch.detect(items, settings.crunch_window_days, settings.crunch_min_count,
                         settings.crunch_min_weight, settings.crunch_rule_version)


@router.get("/crunch", response_model=list[s.CrunchOut])
def get_crunch(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [s.CrunchOut(**p.__dict__) for p in _crunch(user, db)]


@router.get("/calendar")
def calendar(start: date, end: date, user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = [_a_out(a) for a in _user_assessments(user, db, "confirmed") if a.due_date and start <= a.due_date <= end]
    plan = _latest_plan(user, db)
    blocks = [s.BlockOut.model_validate(b) for b in (plan.blocks if plan else [])
              if b.end_date >= start and b.start_date <= end]
    return {"assessments": items, "blocks": blocks,
            "crunch": [s.CrunchOut(**p.__dict__) for p in _crunch(user, db) if p.end >= start and p.start <= end]}


# ---------- plans (R8, R9, R10, R11) ----------
def _latest_plan(user: User, db: Session, offset: int = 0) -> Plan | None:
    return db.scalars(select(Plan).where(Plan.user_id == user.id).order_by(Plan.version.desc())
                      .offset(offset).limit(1)).first()


def _slots(user: User, db: Session) -> list[planner.Slot]:
    return [planner.Slot(r.weekday, r.start_time, r.end_time)
            for r in db.scalars(select(ReservedHours).where(ReservedHours.user_id == user.id))]


def _plan_out(plan: Plan, user: User, db: Session) -> s.PlanOut:
    full = sorted(planner.full_weekdays(_slots(user, db), settings.full_day_hours))
    blocks = sorted(plan.blocks, key=lambda b: (b.start_date, b.id))
    return s.PlanOut(id=plan.id, version=plan.version, trigger=plan.trigger, created_at=plan.created_at,
                     is_valid=plan.is_valid, validation_errors=plan.validation_errors, full_weekdays=full,
                     blocks=[s.BlockOut.model_validate(b) for b in blocks])


@router.post("/plans", response_model=s.PlanOut, status_code=201)
def create_plan(trigger: str = "manual", user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = term_of(db)
    tasks = [planner.Task(a.id, a.course.code, a.title, a.type, a.due_date, a.weight_percent)
             for a in _user_assessments(user, db, "confirmed") if a.due_date]
    result = planner.generate(tasks, _slots(user, db), settings.today(), t.end_date,
                              settings.full_day_hours, settings.max_blocks_per_day)
    if settings.llm_labels:
        _llm_labels(result.blocks)
    prev = _latest_plan(user, db)
    plan = Plan(user_id=user.id, version=(prev.version + 1 if prev else 1), trigger=trigger[:64],
                is_valid=result.is_valid, validation_errors=result.errors + result.warnings)
    plan.blocks = [PlanBlock(assessment_id=b.assessment_id, task_label=b.label, start_date=b.start, end_date=b.end)
                   for b in result.blocks]
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _plan_out(plan, user, db)


def _llm_labels(blocks: list[planner.Block]) -> None:
    """Optional: one batched call rewords labels; dates never change, template stays on failure."""
    try:
        provider = get_provider(settings)
        schema = {"type": "object", "properties": {"labels": {"type": "array", "items": {"type": "string"}}},
                  "required": ["labels"]}
        prompt = "Rewrite each study task as a short, friendly label (max 8 words), same order:\n" + \
                 "\n".join(f"- {b.label}" for b in blocks)
        reply = provider.complete_json("You write concise study-plan labels.", prompt, schema)
        labels = reply.data.get("labels", [])
        if len(labels) == len(blocks):
            for b, lab in zip(blocks, labels):
                if isinstance(lab, str) and lab.strip():
                    b.label = lab.strip()[:255]
    except Exception:
        pass


@router.get("/plans/latest", response_model=s.PlanOut | None)
def latest_plan(user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = _latest_plan(user, db)
    return _plan_out(plan, user, db) if plan else None


@router.get("/plans/latest/diff")
def plan_diff(user: User = Depends(current_user), db: Session = Depends(get_db)):
    new, old = _latest_plan(user, db), _latest_plan(user, db, offset=1)
    if new is None or old is None:
        return {"previous_version": None, "added": [], "removed": [], "moved": [], "unchanged": []}

    def blocks(p: Plan):
        return [planner.Block(b.assessment_id, b.task_label, b.start_date, b.end_date)
                for b in p.blocks if b.assessment_id is not None]

    return {"previous_version": old.version, **planner.diff(blocks(old), blocks(new))}


@router.get("/export.ics")
def export_ics(user: User = Depends(current_user), db: Session = Depends(get_db)):
    events = []
    for a in _user_assessments(user, db, "confirmed"):
        if a.due_date:
            w = f" ({a.weight_percent:g}%)" if a.weight_percent is not None else ""
            events.append({"uid": f"due-{a.id}", "summary": f"DUE: {a.course.code} {a.title}{w}",
                           "start": a.due_date, "end": a.due_date, "description": a.source_excerpt})
    plan = _latest_plan(user, db)
    for b in plan.blocks if plan else []:
        events.append({"uid": f"block-{b.id}", "summary": b.task_label, "start": b.start_date, "end": b.end_date})
    return Response(build_calendar(events), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="akedu-plan.ics"'})
