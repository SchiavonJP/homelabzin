from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


def uid():
    return str(uuid4())


def now():
    return datetime.now(UTC).isoformat()


class User(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str


class Source(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    path: str = Field(unique=True, index=True)
    title: str
    version: str = ""
    checked_at: str = ""
    captured_at: str = ""
    state: str = "pending"
    error: str = ""
    approved: bool = False
    provider: str = 'silverbullet'
    connection_id: str = 'silverbullet'
    external_id: str = ''
    permalink: str = ''
    family_id: str = ''


class Version(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("source_id", "hash"),)
    id: str = Field(default_factory=uid, primary_key=True)
    source_id: str = Field(index=True)
    hash: str
    body: str
    title: str = ''
    captured_at: str = Field(default_factory=now)
    etag: str
    state: str = "pending"
    operation_id: str = ""
    error: str = ""


class Finding(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    key: str = Field(unique=True)
    kind: str
    text: str
    reason: str
    evidence: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: str = Field(default_factory=now)
    state: str = "proposed"
    revision: int = 0


class Question(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    issue: str = Field(unique=True)
    text: str
    reason: str
    evidence: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    state: str = "open"
    answer: str = ""
    disposition: str = "tentative"
    revision: int = 0
    updated_at: str = Field(default_factory=now)


class Feedback(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    key: str = Field(unique=True)
    question_id: str = Field(index=True)
    answer: str
    disposition: str
    origin: str
    created_at: str = Field(default_factory=now)
    operation_id: str = ""
    state: str = "pending"


class Run(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    key: str = Field(unique=True)
    state: str = "queued"
    stage: str = "queued"
    created_at: str = Field(default_factory=now)
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    stop_requested: bool = False
    consolidation_id: str = ""
    draft_hash: str = ""
    result: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Schedule(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    enabled: bool = False
    hour: int = 3
    minute: int = 0
    timezone: str = "America/Sao_Paulo"
    revision: int = 0
    last_due: str = ""


class Publication(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    etag: str = ""
    body: str = ""
    published_at: str = ""
    state: str = "not_published"
    error: str = ""
    pending_body: str = ""
    pending_etag: str = ""


class Artifact(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class ReviewPage(SQLModel, table=True):
    path: str = Field(primary_key=True)
    kind: str
    entity_id: str = Field(index=True)
    body: str = ""
    etag: str = ""
    pending_body: str = ""
    state: str = "pending"
    error: str = ""
    published_at: str = ""


class Event(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    at: str = Field(default_factory=now)
    kind: str
    detail: str


class Heartbeat(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    at: str = Field(default_factory=now)


class AutomationPolicy(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    revision: int = 0
    mode: str = 'manual'
    paused: bool = True
    folders: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    exclusions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    notes_per_day: int = 10
    minutes_per_day: int = 20
    approved_at: str = ''


class IntakeNote(SQLModel, table=True):
    path: str = Field(primary_key=True)
    source_id: str = ''
    version: str = ''
    state: str = 'unread'
    inventory: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    verified_at: str = ''
    discovered_at: str = Field(default_factory=now)
    worked_at: str = ''
    attempts: int = 0
    next_attempt_at: str = ''
    error: str = ''


class IntakeSection(SQLModel, table=True):
    __table_args__ = (UniqueConstraint('source_id', 'version', 'number'),)
    id: str = Field(primary_key=True)
    source_id: str = Field(index=True)
    version: str
    number: int
    start: int
    end: int
    kind: str = 'original'
    document_id: str = ''
    state: str = 'pending'
    operation_id: str = ''
    error: str = ''
    attempts: int = 0
    next_attempt_at: str = ''
    reused_from: str = ''


class SourceConnection(SQLModel, table=True):
    id: str = Field(primary_key=True)
    provider: str = 'affine'
    workspace: str = ''
    exclusions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    approved_at: str = ''
    paused: bool = True
    revision: int = 0


class SourceRelationship(SQLModel, table=True):
    __table_args__ = (UniqueConstraint('source_id', 'target_id'),)
    id: str = Field(default_factory=uid, primary_key=True)
    source_id: str
    target_id: str
    state: str = 'suggested'
    method: str = 'title'
    revision: int = 0


class AutomationRun(SQLModel, table=True):
    run_id: str = Field(primary_key=True)
    policy: dict[str, Any] = Field(sa_column=Column(JSON))
    day: str = ''
    limit_seconds: float = 0
    charged_seconds: float = 0
    accounted: bool = False


class DailyUsage(SQLModel, table=True):
    day: str = Field(primary_key=True)
    seconds: float = 0
    notes: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class ReferenceItem(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    url: str = Field(unique=True, index=True)
    title: str = ''
    description: str = ''
    context: str = ''
    kind: str = 'reference'
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    suggested_tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    projects: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    bookmark_id: str = ''
    candidate_hash: str = ''
    approved_hash: str = ''
    approval_origin: str = ''
    revision: int = 0
    state: str = 'catalogued'
    error: str = ''
    organized_hash: str = ''
    updated_at: str = Field(default_factory=now)


class ReferenceMention(SQLModel, table=True):
    id: str = Field(primary_key=True)
    reference_id: str = Field(index=True)
    path: str
    version: str
    title: str = ''
    start: int = 0
    end: int = 0
    context: str = ''
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    active: bool = True


class ReferenceCapture(SQLModel, table=True):
    __table_args__ = (UniqueConstraint('reference_id', 'hash'),)
    id: str = Field(default_factory=uid, primary_key=True)
    reference_id: str = Field(index=True)
    hash: str
    body_hash: str
    title: str
    body: str
    article_body: str
    annotations: str = ''
    final_url: str
    captured_at: str = Field(default_factory=now)


class KnowledgeRelation(SQLModel, table=True):
    id: str = Field(primary_key=True)
    source_id: str = Field(index=True)
    target_id: str = Field(index=True)
    kind: str = 'related-to'
    origin: str = 'metadata'
    state: str = 'suggested'
    reason: str = ''
    evidence: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    revision: int = 0
