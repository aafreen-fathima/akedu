"""Request and response bodies."""
from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator

TYPES = {"assignment", "quiz", "midterm", "final", "project", "presentation", "lab", "other"}


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str


class SlotIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    label: str = Field(default="", max_length=64)


class SlotOut(SlotIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_id: int
    status: str
    provider: str
    model: str
    attempts: int
    item_count: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class DocumentOut(BaseModel):
    id: int
    filename: str
    page_count: int
    course_code: str | None
    uploaded_at: datetime
    job: JobOut | None


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    title: str


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: int
    course_code: str
    title: str
    type: str
    due_date: date | None
    due_time: time | None
    weight_percent: float | None
    source_excerpt: str
    source_page: int | None
    review_note: str | None
    status: str


class AssessmentCreate(BaseModel):
    course_code: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    type: str = "assignment"
    due_date: date
    due_time: time | None = None
    weight_percent: float | None = Field(default=None, ge=0, le=100)

    @field_validator("type")
    @classmethod
    def _type(cls, v):
        if v not in TYPES:
            raise ValueError(f"type must be one of {sorted(TYPES)}")
        return v


class AssessmentPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    type: str | None = None
    due_date: date | None = None
    due_time: time | None = None
    weight_percent: float | None = Field(default=None, ge=0, le=100)
    status: str | None = None

    @field_validator("type")
    @classmethod
    def _type(cls, v):
        if v is not None and v not in TYPES:
            raise ValueError(f"type must be one of {sorted(TYPES)}")
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v is not None and v not in {"extracted", "confirmed"}:
            raise ValueError("status must be 'extracted' or 'confirmed'")
        return v


class ConfirmIn(BaseModel):
    ids: list[int]


class CrunchOut(BaseModel):
    start: date
    end: date
    assessment_ids: list[int]
    count: int
    total_weight: float
    reasons: list[str]
    rule_version: str


class BlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assessment_id: int | None
    task_label: str
    start_date: date
    end_date: date


class PlanOut(BaseModel):
    id: int
    version: int
    trigger: str
    created_at: datetime
    is_valid: bool
    validation_errors: list[str]
    full_weekdays: list[int]
    blocks: list[BlockOut]


class TermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    start_date: date
    end_date: date
    breaks: list
    today: date
