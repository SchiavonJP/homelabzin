import contextlib
import contextvars
from datetime import UTC, datetime, timedelta
from pathlib import Path
import secrets
from typing import Literal
from urllib.parse import quote
from uuid import UUID

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select
from sqlalchemy import case, func
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings
from app.db import initialize, make_engine
from app.models import Event, Feedback, Finding, Heartbeat, Publication, Question, Run, Schedule, Source, User, Version, ReviewPage, Artifact, now
from app.security import ALGORITHM, create_access_token, verify_password
from app.services import answer_question, current_versions, enqueue, has_current_evidence, review_finding, request_publication
from app.review import question_path, finding_path, source_permalink
from app import sync_check, automation, connections
from app import library_api, references
from mcp.types import ToolAnnotations
from app.source_selection import catalogue, choose, selection
from app.vault import DomainError, Vault, digest, eligible, source_path

actor_context = contextvars.ContextVar("xereta_actor", default=None)
bearer = HTTPBearer(auto_error=False)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class RunInput(Input):
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9:_-]+$")


class Answer(Input):
    answer: str = Field(max_length=12000)
    disposition: Literal["tentative", "confirmed", "decision-approved", "deferred"]
    expected_revision: int = Field(ge=0)


class Decision(Input):
    state: Literal["accepted", "rejected"]
    expected_revision: int = Field(ge=0)


class ScheduleInput(Input):
    enabled: bool
    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)
    expected_revision: int = Field(ge=0)


class SourceSelectionInput(Input):
    paths: list[str] = Field(min_length=1, max_length=3)
    expected_revision: int = Field(ge=0)


class ConnectionScope(Input):
    workspace: str = Field(min_length=1, max_length=128)
    exclusions: list[str] = Field(default_factory=list, max_length=10000)
    expected_revision: int = Field(ge=0)


class RelationshipInput(Input):
    state: Literal['linked', 'unlinked']
    expected_revision: int = Field(ge=0)


class ScopeInput(Input):
    folders: list[str] = Field(max_length=100)
    exclusions: list[str] = Field(default_factory=list, max_length=100)


class AutomationInput(ScopeInput):
    mode: Literal['manual', 'automatic']
    notes_per_day: int = Field(default=10, ge=1, le=10)
    minutes_per_day: int = Field(default=20, ge=1, le=20)
    expected_revision: int = Field(ge=0)


class RevisionInput(Input):
    expected_revision: int = Field(ge=0)


class ResumeInput(RevisionInput, RunInput):
    pass


def serialize(item):
    return item.model_dump() if item else None


def authenticate(token, settings, engine):
    if secrets.compare_digest(token, settings.agent_read_token.get_secret_value()):
        return "reader"
    try:
        payload = jwt.decode(token, settings.secret_key.get_secret_value(), algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
        with Session(engine) as s:
            if s.get(User, payload["sub"]):
                return "owner"
    except (jwt.PyJWTError, KeyError, TypeError):
        pass
    raise HTTPException(401, "Sessão inválida ou expirada")


class VaultLink:
    def __init__(self, settings):
        self.settings = settings

    def permalink(self, path):
        return self.settings.public_silverbullet_url + "/" + quote(path.removesuffix(".md"), safe="/")


def overview(engine, settings):
    with Session(engine) as s:
        sources = list(s.exec(select(Source).order_by(Source.path)))
        questions = list(s.exec(select(Question).where(Question.state.notin_(["withdrawn", "queued"])).order_by(case((Question.state.in_(["open", "answered"]), 0), else_=1), Question.updated_at.desc()).limit(50)))
        findings = list(s.exec(select(Finding).where(Finding.state != "superseded").order_by(Finding.created_at.desc()).limit(50)))
        runs = list(s.exec(select(Run).order_by(Run.created_at.desc()).limit(30)))
        automatic_policy = automation.policy(s)
        beat = s.get(Heartbeat, 1)
        worker_ok = bool(beat and (datetime.now(UTC) - datetime.fromisoformat(beat.at)).total_seconds() < 240)
        return {"name": "Xereta", "automation": automation.summary(s), "source_selection": selection(s, settings), "sources": [{**serialize(x), "evidence_family": connections.evidence_family(s, x), "active_scope": automatic_policy.mode == "automatic" and automation.in_scope(x.path, automatic_policy), "permalink": source_permalink(s, VaultLink(settings), x)} for x in sources],
            "questions": [{**serialize(q), "evidence_current": has_current_evidence(s, q.evidence), "note_url": VaultLink(settings).permalink(question_path(q))} for q in questions],
            "findings": [{**serialize(f), "evidence_current": has_current_evidence(s, f.evidence), "note_url": VaultLink(settings).permalink(finding_path(f))} for f in findings],
            "runs": [serialize(x) for x in runs], "schedule": serialize(s.get(Schedule, 1)),
            "publication": {k: v for k, v in serialize(s.get(Publication, 1)).items() if k not in ("body", "pending_body")},
            "worker": {"healthy": worker_ok, "last_seen": beat.at if beat else None},
            "gates": {"publication": settings.publish_enabled, "scheduling": settings.acceptance_passed,
                      "owner_feedback": bool(s.exec(select(Feedback).where(Feedback.origin.in_(["web", "vault"]))).first())},
            "review": {"layout": "files", "index_url": VaultLink(settings).permalink("space/_AgentKnowledge/Index.md"),
                "pages": [{"path": p.path, "kind": p.kind, "entity_id": p.entity_id, "state": p.state, "error": p.error}
                          for p in s.exec(select(ReviewPage))],
                "outbox": (s.get(Artifact, "review:outbox").value.get("state") if s.get(Artifact, "review:outbox") else "complete"),
                "legacy": s.get(Artifact, "review:layout-v2").value if s.get(Artifact, "review:layout-v2") else None},
            "sync_check": sync_check.status(s), "checked_at": now()}


def create_app(settings=None):
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    mcp = FastMCP("Xereta", stateless_http=True, json_response=True, streamable_http_path="/",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "192.168.0.213:*", "xereta.joaopaulo.me", "testserver"],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://192.168.0.213:3101", "https://xereta.joaopaulo.me"]))

    @contextlib.asynccontextmanager
    async def lifespan(app):
        initialize(engine, settings)
        async with mcp.session_manager.run():
            yield
        engine.dispose()

    app = FastAPI(title="Xereta", version="0.6.0", lifespan=lifespan)
    app.state.engine, app.state.settings = engine, settings

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse({"detail": error.code}, status_code=error.status)

    @app.exception_handler(Exception)
    async def internal_error(request, error):
        return JSONResponse({"detail": "internal_error"}, status_code=500)

    def actor(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if not credentials:
            raise HTTPException(401, "Entre para continuar")
        return authenticate(credentials.credentials, settings, engine)

    def owner(role=Depends(actor)):
        if role != "owner":
            raise HTTPException(403, "Esta ação exige confirmação do proprietário")
        return role

    app.include_router(library_api.router(engine,settings,actor,owner))

    class MCPAuthentication(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if not request.url.path.startswith("/mcp"):
                return await call_next(request)
            raw = request.headers.get("authorization", "")
            if not raw.startswith("Bearer "):
                return JSONResponse({"detail": "authentication_required"}, 401)
            try:
                role = authenticate(raw[7:], settings, engine)
            except HTTPException:
                return JSONResponse({"detail": "invalid_token"}, 401)
            context = actor_context.set(role)
            try:
                return await call_next(request)
            finally:
                actor_context.reset(context)
    app.add_middleware(MCPAuthentication)

    @app.get("/health/live")
    def live():
        return {"status": "ok", "name": "Xereta"}

    @app.get("/health/ready")
    def ready():
        result = overview(engine, settings)
        return JSONResponse({"status": "ok" if result["worker"]["healthy"] else "degraded"},
                            status_code=200 if result["worker"]["healthy"] else 503)

    @app.post("/api/v1/login/access-token")
    def login(body: Login):
        with Session(engine) as s:
            # Persist a small rate limit across restarts, without storing IPs/passwords.
            cutoff = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
            failures = list(s.exec(select(Event).where(Event.kind == "login_failure", Event.at > cutoff)))
            if len(failures) >= 10:
                raise HTTPException(429, "Aguarde um minuto antes de tentar novamente")
            user = s.exec(select(User).where(User.email == body.email)).first()
            if not user or not verify_password(body.password, user.password_hash)[0]:
                s.add(Event(kind="login_failure", detail="invalid_credentials"))
                s.commit()
                raise HTTPException(401, "Email ou senha inválidos")
            return {"access_token": create_access_token(user.id, timedelta(hours=settings.session_hours),
                                                        settings.secret_key.get_secret_value()), "token_type": "bearer"}

    @app.get("/api/v1/xereta/overview", dependencies=[Depends(actor)])
    def get_overview():
        return overview(engine, settings)

    @app.get('/api/v1/xereta/source-catalog', dependencies=[Depends(owner)])
    def get_source_catalog():
        with Session(engine) as s, contextlib.closing(Vault(settings)) as vault, contextlib.closing(connections.Readers(vault, settings)) as readers:
            return catalogue(s, settings, readers)

    @app.put('/api/v1/xereta/source-selection', dependencies=[Depends(owner)])
    def update_source_selection(body: SourceSelectionInput):
        with Session(engine) as s, contextlib.closing(Vault(settings)) as vault, contextlib.closing(connections.Readers(vault, settings)) as readers:
            return choose(s, settings, readers, body.paths, body.expected_revision)

    @app.get('/api/v1/xereta/connections', dependencies=[Depends(owner)])
    def source_connections():
        with Session(engine) as s:
            return {**connections.statuses(s, settings), 'relationships': connections.relationships(s)}

    @app.post('/api/v1/xereta/connections/affine/preview', dependencies=[Depends(owner)])
    def preview_affine(body: ConnectionScope):
        with contextlib.closing(connections.AffineReader(settings)) as reader:
            rows = reader.inventory(body.workspace)
        return {'workspace': body.workspace, 'notes': rows,
                'included': sum(connections.identity(x['path'])[1] not in body.exclusions for x in rows),
                'excluded': sum(connections.identity(x['path'])[1] in body.exclusions for x in rows)}

    @app.put('/api/v1/xereta/connections/affine/scope', dependencies=[Depends(owner)])
    def save_affine(body: ConnectionScope):
        with Session(engine) as s:
            return connections.save_scope(s, settings, body.workspace, body.exclusions, body.expected_revision)

    @app.post('/api/v1/xereta/connections/affine/pause', dependencies=[Depends(owner)])
    def pause_affine(body: RevisionInput):
        with Session(engine) as s:
            return connections.control(s, body.expected_revision, True)

    @app.post('/api/v1/xereta/connections/affine/resume', dependencies=[Depends(owner)])
    def resume_affine(body: RevisionInput):
        with contextlib.closing(connections.AffineReader(settings)) as reader:
            reader.call('POST', '/status', {})
        with Session(engine) as s:
            return connections.control(s, body.expected_revision, False)

    @app.post('/api/v1/xereta/connections/affine/check', dependencies=[Depends(owner)])
    def check_affine():
        with Session(engine) as s:
            try:
                with contextlib.closing(connections.AffineReader(settings)) as reader:
                    reader.call('POST', '/status', {})
                connections.health(s, 'affine', 'healthy')
            except DomainError as error:
                connections.health(s, 'affine', 'reauth_required' if error.code == 'affine_reauth_required' else 'unavailable', error.code)
                raise
            return connections.statuses(s, settings)

    @app.patch('/api/v1/xereta/source-relationships/{relationship_id}', dependencies=[Depends(owner)])
    def update_relationship(relationship_id: str, body: RelationshipInput):
        with Session(engine) as s:
            return connections.change_relationship(s, relationship_id, body.state, body.expected_revision)

    @app.get('/api/v1/xereta/automation', dependencies=[Depends(owner)])
    def get_automation():
        with Session(engine) as s:
            return automation.summary(s, True)

    @app.post('/api/v1/xereta/automation/preview', dependencies=[Depends(owner)])
    def preview_automation(body: ScopeInput):
        with contextlib.closing(Vault(settings)) as vault:
            return automation.preview(vault, body.folders, body.exclusions)

    @app.put('/api/v1/xereta/automation', dependencies=[Depends(owner)])
    def save_automation(body: AutomationInput):
        with Session(engine) as s:
            return automation.save_policy(s, **body.model_dump())

    @app.post('/api/v1/xereta/automation/pause', dependencies=[Depends(owner)])
    def pause_automation(body: RevisionInput):
        with Session(engine) as s:
            return automation.pause(s, body.expected_revision)

    @app.post('/api/v1/xereta/automation/resume', dependencies=[Depends(owner)], status_code=202)
    def resume_automation(body: ResumeInput):
        with Session(engine) as s:
            return automation.resume(s, settings, body.expected_revision, body.idempotency_key)

    @app.get('/api/v1/xereta/automation/queue', dependencies=[Depends(owner)])
    def automatic_queue(offset: int = Query(default=0, ge=0), limit: int = Query(default=30, ge=1, le=100)):
        with Session(engine) as s:
            return automation.queue(s, automation.policy(s), offset, limit)

    @app.get('/api/v1/xereta/review-queue', dependencies=[Depends(owner)])
    def get_review_queue(kind: Literal['question', 'finding'], state: str = Query(default='', max_length=40),
                         q: str = Query(default='', max_length=500), offset: int = Query(default=0, ge=0),
                         limit: int = Query(default=30, ge=1, le=100)):
        model = Question if kind == 'question' else Finding
        with Session(engine) as s:
            statement = select(model).where(model.state.notin_(['withdrawn', 'superseded']))
            if state:
                statement = statement.where(model.state.in_(['open', 'answered']) if state == 'pending' else model.state == state)
            if q:
                statement = statement.where(func.lower(model.text).contains(q.lower(), autoescape=True))
            from sqlalchemy import func
            total = s.exec(select(func.count()).select_from(statement.subquery())).one()
            ordering = Question.updated_at.desc() if kind == 'question' else Finding.created_at.desc()
            rows = s.exec(statement.order_by(ordering, model.id).offset(offset).limit(limit)).all()
            return {'items': [{**serialize(x), 'evidence_current': has_current_evidence(s, x.evidence),
                'note_url': VaultLink(settings).permalink(question_path(x) if kind == 'question' else finding_path(x))} for x in rows],
                'total': total, 'offset': offset, 'limit': limit}

    @app.get("/api/v1/xereta/sources/{source_id}/versions/{version_hash}", dependencies=[Depends(actor)])
    def get_version(source_id: str, version_hash: str):
        with Session(engine) as s:
            source = s.get(Source, source_id)
            version = s.exec(select(Version).where(Version.source_id == source_id, Version.hash == version_hash)).first()
            if not source or not version:
                raise HTTPException(404, "Versão não encontrada")
            return {**serialize(version), "source": serialize(source),
                    "permalink": source_permalink(s, VaultLink(settings), source)}

    @app.post("/api/v1/xereta/runs", status_code=202, dependencies=[Depends(owner)])
    def request_run(body: RunInput):
        with Session(engine) as s:
            return serialize(enqueue(s, body.idempotency_key))

    @app.post("/api/v1/xereta/runs/{run_id}/retry", status_code=202, dependencies=[Depends(owner)])
    def retry_run(run_id: str, body: RunInput):
        with Session(engine) as s:
            run = s.get(Run, run_id)
            if not run or run.state not in ("failed", "stopped"):
                raise DomainError("run_not_retryable")
            # Only known terminal failures get a new operation ID on explicit retry.
            # Unknown acknowledgements keep their ID and are reconciled instead.
            for version in s.exec(select(Version).where(Version.state == "remote_failed")).all():
                s.add(Event(kind="operation_retry", detail=version.operation_id))
                version.operation_id, version.state, version.error = "", "pending", ""
                s.add(version)
            s.commit()
            return serialize(enqueue(s, body.idempotency_key))

    @app.post("/api/v1/xereta/runs/{run_id}/stop", dependencies=[Depends(owner)])
    def stop_run(run_id: str):
        with Session(engine) as s:
            run = s.get(Run, run_id)
            if not run or run.state not in ("queued", "running"):
                raise DomainError("run_not_active")
            run.stop_requested = True
            if run.state == "queued":
                run.state = "stopped"
                run.finished_at = now()
            s.add(run)
            s.commit()
            return serialize(run)

    @app.patch("/api/v1/xereta/questions/{question_id}", dependencies=[Depends(owner)])
    def feedback(question_id: str, body: Answer):
        with Session(engine) as s:
            return serialize(answer_question(s, question_id, body.answer, body.disposition, body.expected_revision))

    @app.patch("/api/v1/xereta/findings/{finding_id}", dependencies=[Depends(owner)])
    def review_finding_endpoint(finding_id: str, body: Decision):
        with Session(engine) as s:
            return serialize(review_finding(s, finding_id, body.state, body.expected_revision))

    @app.post("/api/v1/xereta/review/sync", dependencies=[Depends(owner)], status_code=202)
    def sync_review():
        with Session(engine) as s:
            request_publication(s)
            s.commit()
            return {"state": "queued"}

    @app.post("/api/v1/xereta/sync-check", dependencies=[Depends(owner)])
    def start_sync_check():
        with Session(engine) as s, contextlib.closing(Vault(settings)) as vault:
            return sync_check.start(s, vault)

    @app.post("/api/v1/xereta/sync-check/{identifier}/verify", dependencies=[Depends(owner)])
    def verify_sync_check(identifier: UUID):
        with Session(engine) as s, contextlib.closing(Vault(settings)) as vault:
            return sync_check.verify(s, vault, str(identifier))

    @app.put("/api/v1/xereta/schedule", dependencies=[Depends(owner)])
    def update_schedule(body: ScheduleInput):
        with Session(engine) as s:
            schedule = s.exec(select(Schedule).with_for_update()).first()
            if schedule.revision != body.expected_revision:
                raise DomainError("schedule_revision_conflict")
            if body.enabled and not settings.acceptance_passed:
                raise DomainError("acceptance_gates_pending")
            if body.enabled and (not schedule.enabled or (schedule.hour, schedule.minute) != (body.hour, body.minute)):
                from zoneinfo import ZoneInfo
                baseline = datetime.now(UTC).astimezone(ZoneInfo(schedule.timezone))
                due = baseline.replace(hour=body.hour, minute=body.minute, second=0, microsecond=0)
                if baseline < due:
                    due -= timedelta(days=1)
                schedule.last_due = due.isoformat()
            schedule.enabled, schedule.hour, schedule.minute = body.enabled, body.hour, body.minute
            schedule.revision += 1
            s.add(schedule)
            s.commit()
            return serialize(schedule)

    def require_owner():
        if actor_context.get() != "owner":
            raise DomainError("owner_authorization_required", 403)

    @mcp.tool()
    def xereta_status() -> dict:
        """Estado da digestão, perguntas, decisões e agendamento do Xereta."""
        return overview(engine, settings)

    @mcp.tool()
    def xereta_request_run(idempotency_key: str) -> dict:
        """Solicita execução limitada. Requer credencial do proprietário."""
        require_owner()
        return request_run(RunInput(idempotency_key=idempotency_key))

    @mcp.tool()
    def xereta_answer_question(question_id: str, answer: str, disposition: str, expected_revision: int) -> dict:
        """Registra resposta explicitamente autorizada pelo proprietário."""
        require_owner()
        return feedback(question_id, Answer(answer=answer, disposition=disposition, expected_revision=expected_revision))

    @mcp.tool()
    def list_notes(subdir: str = "") -> dict:
        """Lista as notas do vault compartilhado; prefixos são relativos ao vault."""
        if subdir and (".." in subdir.split("/") or subdir.startswith("/") or "\\" in subdir):
            raise DomainError("invalid_vault_path", 422)
        with contextlib.closing(Vault(settings)) as vault:
            rows = vault.inventory()
            notes = [x["path"].removeprefix("space/") for x in rows if x["path"].startswith("space/" + subdir)]
            return {"notes": notes, "total": len(notes)}

    @mcp.tool()
    def read_note(note_path: str) -> dict:
        """Lê uma nota e sua versão, preservando o Markdown original."""
        with contextlib.closing(Vault(settings)) as vault:
            path = source_path("space/" + note_path)
            if not eligible(path):
                raise DomainError("note_not_available", 403)
            c = vault.capture(path)
            return {"path": note_path, "content": c.body, "frontmatter": {}, "version": c.hash}

    @mcp.tool()
    def search_notes(q: str, max_results: int = 20) -> dict:
        """Busca texto literal nas notas do piloto, com citações verificáveis."""
        if not q or len(q) > 500 or not 1 <= max_results <= 50:
            raise DomainError("invalid_search", 422)
        with Session(engine) as s:
            sources, versions = current_versions(s)
            rows = [{"file": x.path.removeprefix("space/"), "snippet": versions[x.id].body[
                max(0, versions[x.id].body.lower().find(q.lower())-100):][:500], "frontmatter": {}}
                for x in sources if x.id in versions and q.lower() in versions[x.id].body.lower()][:max_results]
            return {"query": q, "results": rows, "total": len(rows)}

    @mcp.tool()
    def write_note(path: str, content: str, frontmatter_data: dict | None = None, expected_revision: str | None = None) -> dict:
        """Escrita de notas desativada. Use xereta_answer_question para responder com revisão."""
        require_owner()
        raise DomainError("use_xereta_review_actions", 403)

    @mcp.tool()
    def get_backlinks(note_path: str) -> dict:
        needle = "[[" + Path(note_path).stem + "]]"
        return {"note": note_path, "backlinks": [r["file"] for r in search_notes(needle, 50)["results"]],
                "total": len(search_notes(needle, 50)["results"])}

    def local_read(base, relative):
        root, target = Path(base).resolve(), (Path(base) / relative).resolve()
        if not target.is_relative_to(root) or not target.is_file() or target.stat().st_size > 1024 * 1024:
            raise DomainError("local_file_not_available", 404)
        return target.read_text()

    @mcp.tool()
    def list_skills() -> dict:
        rows = [str(p.relative_to("/skills")) for p in Path("/skills").rglob("*.md") if p.is_file()]
        return {"skills": rows, "total": len(rows)}

    @mcp.tool()
    def get_skill(skill_path: str) -> dict:
        return {"path": skill_path, "content": local_read("/skills", skill_path)}

    @mcp.tool()
    def search_skills(q: str, max_results: int = 10) -> dict:
        if not q or len(q) > 500 or not 1 <= max_results <= 50:
            raise DomainError("invalid_search", 422)
        rows = [{"file": p, "snippet": get_skill(p)["content"][:300], "frontmatter": {}}
                for p in list_skills()["skills"] if q.lower() in get_skill(p)["content"].lower()][:max_results]
        return {"query": q, "results": rows, "total": len(rows)}

    @mcp.tool()
    def get_user_model() -> dict:
        try:
            return {"content": local_read("/opt/data", "USER.md")}
        except DomainError:
            return {"content": None, "message": "USER.md ainda não existe."}

    @mcp.tool()
    def get_memory() -> dict:
        try:
            return {"content": local_read("/opt/data", "MEMORY.md")}
        except DomainError:
            return {"content": None, "message": "MEMORY.md ainda não existe."}

    @mcp.tool()
    def search_memory(q: str, max_results: int = 10) -> dict:
        if not q or len(q) > 500 or not 1 <= max_results <= 50:
            raise DomainError("invalid_search", 422)
        rows = [{"file": name, "snippet": content[:300], "frontmatter": {}}
                for name, content in (("USER.md", get_user_model()["content"]), ("MEMORY.md", get_memory()["content"]))
                if content and q.lower() in content.lower()][:max_results]
        return {"query": q, "results": rows, "total": len(rows)}

    @mcp.tool()
    def get_recent_synthesis(days: int = 7) -> dict:
        return {"synthesis": [], "message": "Use xereta_status para as sínteses versionadas do Xereta."}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False))
    def search_references(q: str = '', limit: int = 20) -> dict:
        """Search saved references. Catalogue entries do not imply read or verified knowledge."""
        if len(q)>500 or not 1<=limit<=100:raise DomainError('invalid_search',422)
        with Session(engine) as s:return references.list_items(s,q=q,limit=limit)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False))
    def get_related_items(reference_id: str) -> dict:
        """Typed links with their explicit/suggested/reviewed state and provenance."""
        with Session(engine) as s:return {'relations':references.relations(s,reference_id)}

    # Previous pilot REST callers retain their URL; new clients use /xereta.
    class LegacyPaths(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.scope["path"].startswith("/api/v1/curator/"):
                request.scope["path"] = request.scope["path"].replace("/api/v1/curator/", "/api/v1/xereta/", 1)
            return await call_next(request)
    app.add_middleware(LegacyPaths)
    app.mount("/mcp", mcp.streamable_http_app())
    frontend = Path(__file__).parent / "frontend"
    if frontend.exists():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(frontend / "index.html")
    return app
