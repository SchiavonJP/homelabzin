import json
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.memory import Memory, draft
from app.models import Artifact, Event, Feedback, Finding, Heartbeat, Publication, Question, Run, Schedule, Source, Version, now
from app.vault import DomainError, INBOX, Vault, digest, eligible
from app.source_selection import selection
from app.connections import Readers, source_eligible, relate, family, evidence_family

PILOT_LIMIT = 24000
BEGIN, END = "<!-- xereta:generated:start -->", "<!-- xereta:generated:end -->"
STATE_LABELS = {"pending": "Pendente", "submitted": "Em extração", "remote_failed": "Falha na extração",
    "complete": "Memória atualizada", "unavailable": "Indisponível", "oversized": "Nota extensa",
    "open": "Aberta", "answered": "Respondida", "resolved": "Resolvida", "deferred": "Adiada"}
DISPOSITION_LABELS = {"tentative": "rascunho", "confirmed": "confirmada", "decision-approved": "decisão aprovada", "deferred": "adiada"}
DISPOSITION_ALIASES = {v: k for k, v in DISPOSITION_LABELS.items()}



def event(s, kind, detail):
    s.add(Event(kind=kind, detail=detail))


def save_private(path, text):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name("." + str(uuid4()))
    try:
        with temporary.open("xb") as f:
            temporary.chmod(0o600)
            f.write(text if isinstance(text, bytes) else text.encode('utf-8'))
            f.flush()
            import os
            os.fsync(f.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)



def save_captured_snapshot(settings, source, version, capture):
    if not getattr(capture, 'snapshot', None):
        return
    directory = settings.state_path / 'captures' / source.id
    original = directory / (version.hash + '.bin')
    if original.exists():
        if digest(original.read_bytes()) != version.etag:
            raise DomainError('captured_snapshot_integrity_failed')
    elif capture.etag == version.etag:
        save_private(original, capture.snapshot)
    else:
        raise DomainError('original_snapshot_missing_requires_recovery')
    # Render-identical CRDT updates are observations, not new semantic versions.
    # The original version's ETag, snapshot and manifest stay immutable.
    stem = version.hash if capture.etag == version.etag else version.hash + '-' + capture.etag
    binary, metadata = directory / (stem + '.bin'), directory / (stem + '.json')
    if binary.exists():
        if digest(binary.read_bytes()) != capture.etag:
            raise DomainError('captured_snapshot_integrity_failed')
    else:
        save_private(binary, capture.snapshot)
    if not metadata.exists():
        save_private(metadata, json.dumps({'snapshot_sha256': capture.etag,
            'warnings': getattr(capture, 'warnings', []), 'permalink': source.permalink,
            'captured_at': version.captured_at, 'observed_at': now(), 'title': version.title,
            'original_title': getattr(capture, 'original_title', source.title), 'version': version.hash}))


def enqueue(s, key):
    existing = s.exec(select(Run).where(Run.key == key)).first()
    if existing:
        return existing
    # PostgreSQL serializes enqueue requests without holding a transaction for the job.
    if s.bind.dialect.name == "postgresql":
        from sqlalchemy import text
        s.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 1481855590})
    existing = s.exec(select(Run).where(Run.state.in_(["queued", "running"]))).first()
    if existing:
        return existing
    item = Run(key=key)
    from app.automation import attach
    attach(s, item)
    s.add(item)
    event(s, "run_queued", item.id)
    s.commit()
    s.refresh(item)
    return item


def current_versions(s, original_paths=None):
    sources = list(s.exec(select(Source).where(Source.approved == True).order_by(Source.path)))
    if original_paths is not None:
        allowed = set(original_paths)
        sources = [x for x in sources if x.path.startswith('feedback:') or x.path in allowed]
    versions = {}
    for source in sources:
        version = s.exec(select(Version).where(Version.source_id == source.id, Version.hash == source.version)).first()
        if version:
            versions[source.id] = version
    return sources, versions


def capture_sources(s, settings, vault):
    inventory = {x["path"]: x for x in vault.inventory()}
    paths = selection(s, settings)['paths']
    for path in paths:
        if not source_eligible(path):
            raise DomainError("ineligible_pilot_path")
        source = s.exec(select(Source).where(Source.path == path)).first()
        if not source:
            source = Source(path=path, title=Path(path).stem, approved=True)
            s.add(source)
            s.commit()
        source.checked_at = now()
        try:
            if path not in inventory:
                raise DomainError("source_missing_no_automatic_deletion")
            capture = vault.capture(path)
            if path.startswith('affine:'):
                from app.connections import identity, permalink
                workspace, doc = identity(path)
                source.provider, source.connection_id = 'affine', 'affine'
                source.external_id, source.permalink = workspace + '/' + doc, permalink(path)
                source.title = capture.title
            if path.startswith('reference:'):
                source.provider,source.connection_id,source.external_id='references','library',path
                source.permalink=vault.permalink(path);source.title=capture.title
            # Generated files and executable configuration never become evidence.
            if re.search(r"^generated:\s*true\s*$", capture.body[:1000], re.M):
                raise DomainError("generated_source_excluded")
            previous = source.version
            version = s.exec(select(Version).where(Version.source_id == source.id, Version.hash == capture.hash)).first()
            if not version:
                version = Version(source_id=source.id, hash=capture.hash, body=capture.body, etag=capture.etag, title=source.title,
                                  state="oversized" if len(capture.body) > PILOT_LIMIT else "pending")
                s.add(version)
                save_private(settings.state_path / "captures" / source.id / (capture.hash + ".md"), capture.body)
                event(s, "source_changed" if previous else "source_captured", source.id)
            if previous and previous != capture.hash and version.state == "complete":
                event(s, "version_reselected", source.id + ": " + version.hash + ": " + version.operation_id)
                version.state, version.operation_id = "pending", ""
                s.add(version)
            relate(s, source, capture.body, settings)
            save_captured_snapshot(settings, source, version, capture)
            source.version, source.captured_at = capture.hash, version.captured_at
            source.state, source.error = version.state, ""
            if len(capture.body) > PILOT_LIMIT:
                source.state, source.error = 'oversized', 'oversized_sources_pending' 
        except DomainError as error:
            source.error = error.code
            source.state = "unavailable"
            event(s, "capture_failed", source.id + ": " + error.code)
        s.add(source)
        s.commit()
    sources, versions = current_versions(s, original_paths=paths)
    sources = [x for x in sources if source_eligible(x.path)]
    return sources, {x.id: versions[x.id] for x in sources if x.id in versions}


def register_feedback(s, fb):
    """Owner statements have their own identity and immutable captured versions."""
    if fb.disposition == "deferred":
        return None
    q = s.get(Question, fb.question_id)
    finding = s.get(Finding, fb.question_id.removeprefix("finding:")) if fb.question_id.startswith("finding:") else None
    context = q.text if q else finding.text if finding else fb.question_id
    path = "feedback:" + fb.question_id
    source = s.exec(select(Source).where(Source.path == path)).first()
    if source is None:
        source = Source(path=path, title="Resposta do proprietário", approved=True, provider="feedback", connection_id="feedback")
        s.add(source)
    body = f"Contexto: {context}\n\nConfirmação: {fb.disposition}\n\n{fb.answer}"
    hashed = digest(body)
    version = s.exec(select(Version).where(Version.source_id == source.id, Version.hash == hashed)).first()
    if version is None:
        version = Version(source_id=source.id, hash=hashed, body=body, etag="", title="Resposta do proprietário (" + fb.disposition + ")")
        s.add(version)
    if source.version and source.version != hashed and version.state == "complete":
        event(s, "version_reselected", source.id + ": " + hashed + ": " + version.operation_id)
        version.state, version.operation_id = "pending", ""
        s.add(version)
    source.version, source.captured_at = hashed, version.captured_at
    source.state, source.error = version.state, ""
    s.add(source)
    if fb.disposition == "decision-approved" and finding is None:
        key = "owner-decision:" + fb.key
        if not s.exec(select(Finding).where(Finding.key == key)).first():
            s.add(Finding(key=key, kind="decision", text=fb.answer, reason="Decisão explicitamente aprovada pelo proprietário.",
                state="accepted", evidence=[{"source_id": source.id, "version": hashed, "quote": fb.answer}]))
    return source


def source_link(vault, source):
    if source.path.startswith('affine:'):
        from app.connections import permalink
        return permalink(source.path)
    return vault.permalink(source.path) if source.path.startswith("space/") else vault.settings.public_silverbullet_url + "/space/_AgentKnowledge/Inbox"


def has_current_evidence(s, evidence):
    return bool(evidence) and all((source := s.get(Source, e["source_id"]))
        and not source.error and source.version == e["version"] for e in evidence)


def request_publication(s):
    item = s.get(Artifact, "review:outbox") or Artifact(key="review:outbox")
    item.value = {"generation": str(uuid4()), "state": "pending"}
    s.add(item)


def review_finding(s, finding_id, state, expected_revision, origin="web"):
    f = s.exec(select(Finding).where(Finding.id == finding_id).with_for_update()).first()
    if state not in ("accepted", "rejected"):
        raise DomainError("invalid_review_state", 422)
    if not f:
        raise DomainError("finding_not_found", 404)
    if f.state == "superseded":
        raise DomainError("finding_replaced")
    if f.state == state and s.exec(select(Feedback).where(Feedback.key == "finding:" + f.id + ":" + str(f.revision))).first():
        return f
    if f.revision != expected_revision:
        raise DomainError("finding_revision_conflict")
    if not has_current_evidence(s, f.evidence):
        raise DomainError("finding_evidence_changed")
    f.state, f.revision = state, f.revision + 1
    fb = Feedback(key="finding:" + f.id + ":" + str(f.revision), question_id="finding:" + f.id,
        answer=f.text if state == "accepted" else "Descarto este achado ou decisão: " + f.text,
        disposition="decision-approved" if state == "accepted" and f.kind == "decision" else "confirmed", origin=origin)
    s.add(fb)
    register_feedback(s, fb)
    s.add(f)
    event(s, "owner_review", f.id + ": " + state)
    request_publication(s)
    s.commit()
    s.refresh(f)
    return f


def answer_question(s, question_id, answer, disposition, expected_revision, origin="web"):
    q = s.exec(select(Question).where(Question.id == question_id).with_for_update()).first()
    if not q:
        raise DomainError("question_not_found", 404)
    if disposition not in ("tentative", "confirmed", "decision-approved", "deferred"):
        raise DomainError("invalid_disposition", 422)
    if q.state == 'queued':
        raise DomainError('question_not_active')
    if disposition != "deferred" and not has_current_evidence(s, q.evidence):
        raise DomainError("question_evidence_changed")
    answer = answer.strip()
    if not answer and disposition != "deferred":
        raise DomainError("answer_required", 422)
    key = digest(question_id + "\0" + answer + "\0" + disposition + "\0" + str(expected_revision))
    if (q.answer, q.disposition) == (answer, disposition) and s.exec(select(Feedback).where(
            Feedback.question_id == q.id, Feedback.answer == answer, Feedback.disposition == disposition)).first():
        return q
    if q.revision != expected_revision:
        raise DomainError("question_revision_conflict")
    fb = Feedback(key=key, question_id=q.id, answer=answer, disposition=disposition, origin=origin)
    s.add(fb)
    register_feedback(s, fb)
    q.answer, q.disposition = answer, disposition
    q.state = "deferred" if disposition == "deferred" else "answered" if disposition == "tentative" else "resolved"
    q.revision += 1
    q.updated_at = now()
    s.add(q)
    s.flush()
    promote_questions(s)
    s.add(q)
    event(s, "owner_feedback", q.id + ": " + disposition)
    request_publication(s)
    s.commit()
    s.refresh(q)
    return q


QUESTION_BLOCK = re.compile(r"<!-- xereta:question ([a-f0-9-]{36}) revision (\d+) -->\n(.*?)<!-- xereta:end-question -->", re.S)
ANSWER_BLOCK = re.compile(r"### Resposta\n(.*?)\n### Confirmação\n([^\n]*)\n", re.S)


def answers_from(body):
    result = {}
    for block in QUESTION_BLOCK.finditer(body):
        match = ANSWER_BLOCK.search(block[3])
        if not match or block[1] in result:
            raise DomainError("inbox_answer_sections_invalid")
        disposition = match[2].strip()
        result[block[1]] = (int(block[2]), match[1].strip(), DISPOSITION_ALIASES.get(disposition, disposition))
    return result


def mask_answers(body):
    return ANSWER_BLOCK.sub("### Resposta\n<answer>\n### Confirmação\n<disposition>\n", body)


def consume_feedback(s, vault):
    pub = s.get(Publication, 1)
    try:
        incoming = vault.capture(INBOX)
    except DomainError as e:
        if e.code == "vault_file_missing" and not pub.body:
            return None
        raise
    if not pub.body:
        raise DomainError("existing_inbox_requires_explicit_adoption")
    if pub.pending_body and incoming.body == pub.pending_body:
        pub.body, pub.etag, pub.pending_body = incoming.body, incoming.etag, ""
        pub.state, pub.published_at = "published", now()
        s.add(pub)
        s.commit()
    if incoming.body.count(BEGIN) != 1 or incoming.body.count(END) != 1:
        raise DomainError("inbox_generated_markers_changed")
    section = incoming.body.split(BEGIN)[1].split(END)[0]
    old_section = pub.body.split(BEGIN)[1].split(END)[0]
    if mask_answers(section) != mask_answers(old_section):
        raise DomainError("inbox_generated_section_edited")
    previous = answers_from(pub.body)
    for qid, (revision, answer, disposition) in answers_from(incoming.body).items():
        if qid not in previous:
            raise DomainError("unknown_inbox_question")
        if (answer, disposition) != previous[qid][1:]:
            answer_question(s, qid, answer, disposition, revision, "vault")
    return incoming


def safe(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("[", "\\[").replace("]", "\\]").replace("`", "\\`"))


def render_inbox(s, vault, incoming=None):
    sources, versions = current_versions(s)
    lines = [BEGIN, "", "## Pendente de digestão", ""]
    pending = [x for x in sources if x.state != "complete" or x.error]
    lines += [f"- {safe(x.title)} — {safe(STATE_LABELS.get(x.state, "Precisa de revisão"))}" for x in pending] or ["Nenhuma nota pendente no piloto."]
    lines += ["", "## Perguntas abertas", ""]
    questions = list(s.exec(select(Question).where(Question.state != "withdrawn").order_by(Question.updated_at)))
    def evidence(items):
        content = []
        for e in items:
            source = s.get(Source, e["source_id"])
            content += [f"- [{safe(source.title)}]({source_link(vault, source)}) · versão `{e['version'][:12]}`",
                        "> " + safe(e["quote"]).replace("\n", "\n> ")]
        return content
    for q in questions:
        lines += [f"<!-- xereta:question {q.id} revision {q.revision} -->", f"## {safe(q.text)}", "",
                  safe(q.reason), "", "Estado: " + STATE_LABELS.get(q.state, q.state), ""]
        lines += evidence(q.evidence)
        lines += ["", "### Resposta", q.answer, "", "### Confirmação", DISPOSITION_LABELS.get(q.disposition, q.disposition), "",
                  "<!-- xereta:end-question -->", ""]
    if not questions:
        lines += ["Nenhuma pergunta aberta.", ""]
    lines += ["## Conhecimentos e decisões recentes", ""]
    for f in s.exec(select(Finding).order_by(Finding.created_at.desc()).limit(20)):
        if f.state != "rejected" and has_current_evidence(s, f.evidence):
            label = ("Decisão aprovada" if f.state == "accepted" else "Decisão relatada na fonte; requer revisão") if f.kind == "decision" else ("Achado confirmado" if f.state == "accepted" else "Achado proposto")
            lines += [f"### {label}: {safe(f.text)}", ""] + evidence(f.evidence) + [""]
    lines += [END]
    generated = "\n".join(lines)
    if incoming:
        before, after = incoming.body.split(BEGIN)[0], incoming.body.split(END)[1]
        return before + generated + after
    return ("---\ngenerated: true\n---\n\n# Xereta — Caixa de entrada\n\n"
            "Responda abaixo. Em Confirmação, use: rascunho, confirmada, decisão aprovada ou adiada.\n\n"
            + generated + "\n\n## Minhas notas\n\n")


def publish(s, settings, vault):
    pub = s.get(Publication, 1)
    if not settings.publish_enabled:
        pub.state, pub.error = "disabled", "publication_gate_pending"
        s.add(pub)
        s.commit()
        return
    try:
        incoming = consume_feedback(s, vault)
        body = render_inbox(s, vault, incoming)
        if incoming and incoming.body == body:
            pub.state, pub.error, pub.etag = "published", "", incoming.etag
            pub.published_at = pub.published_at or now()
            s.add(pub)
            s.commit()
            return
        pub.pending_body, pub.pending_etag = body, incoming.etag if incoming else ""
        pub.state = "submitting"
        s.add(pub)
        s.commit()
        current = vault.write_inbox(body, incoming.etag if incoming else None)
        pub.body, pub.etag = current.body, current.etag
        pub.pending_body, pub.pending_etag = "", ""
        pub.state, pub.error, pub.published_at = "published", "", now()
        s.add(pub)
        event(s, "inbox_published", INBOX)
        s.commit()
    except DomainError as e:
        pub.state, pub.error = "conflict", e.code
        s.add(pub)
        s.commit()
        raise


def claim_text(text):
    # Exact text preserves units, identifiers and whitespace inside quoted paths.
    return text


def retire_duplicate_proposals(s):
    groups = {}
    for finding in s.exec(select(Finding).where(Finding.state != "superseded").order_by(Finding.created_at, Finding.id)):
        if has_current_evidence(s, finding.evidence):
            groups.setdefault((finding.kind, claim_text(finding.text)), []).append(finding)
    for candidates in groups.values():
        reviewed = [f for f in candidates if f.state in ("accepted", "rejected")]
        # Conflicting owner reviews need human reconciliation.
        if len({f.state for f in reviewed}) > 1 or len(candidates) < 2:
            continue
        canonical = reviewed[0] if reviewed else candidates[0]
        for candidate in candidates:
            if candidate.id == canonical.id:
                continue
            candidate = s.exec(select(Finding).where(Finding.id == candidate.id).with_for_update()).one()
            if candidate.state != "proposed" or s.exec(select(Feedback).where(Feedback.question_id == "finding:" + candidate.id)).first():
                continue
            candidate.state = "superseded"
            s.add(candidate)
            s.add(Artifact(key="finding-alias:" + candidate.id, value={"canonical_id": canonical.id}))
            event(s, "duplicate_proposal_reconciled", candidate.id + ": " + canonical.id)


def store_review(s, items, fingerprint):
    for item in items:
        if item["kind"] == "question":
            issue = item["issue"].strip().casefold()
            q = s.exec(select(Question).where(Question.issue == issue)).first()
            if q is None:
                unresolved = list(s.exec(select(Question).where(Question.state.in_(["open", "answered"]))))
                s.add(Question(issue=issue, text=item["text"], reason=item["reason"], evidence=item["evidence"],
                               state='open' if len(unresolved) < 3 else 'queued'))
                s.flush()
            elif not q.answer and (q.text, q.reason, q.evidence) != (item["text"], item["reason"], item["evidence"]):
                q.text, q.reason, q.evidence = item["text"], item["reason"], item["evidence"]
                q.revision += 1
                s.add(q)
        else:
            current = list(s.exec(select(Finding).where(Finding.kind == item["kind"], Finding.state != "superseded")))
            if any(claim_text(f.text) == claim_text(item["text"]) and has_current_evidence(s, f.evidence) for f in current):
                continue
            key = digest(json.dumps(item, sort_keys=True))
            if not s.exec(select(Finding).where(Finding.key == key)).first():
                s.add(Finding(key=key, kind=item["kind"], text=item["text"], reason=item["reason"], evidence=item["evidence"]))
    s.flush()
    retire_duplicate_proposals(s)
    promote_questions(s)
    s.commit()


def promote_questions(s):
    active = len(s.exec(select(Question).where(Question.state.in_(['open', 'answered']))).all())
    for q in s.exec(select(Question).where(Question.state == 'queued').order_by(Question.updated_at, Question.id)):
        if active >= 3:
            break
        if has_current_evidence(s, q.evidence):
            q.state, q.updated_at = 'open', now()
            s.add(q)
            active += 1


def remaining_run_seconds(started_at, instant=None):
    """A resumed run keeps its original wall-clock budget, including downtime."""
    try:
        started = datetime.fromisoformat(started_at)
        if started.tzinfo is None:
            raise ValueError()
    except (ValueError, TypeError):
        raise DomainError("run_budget_timestamp_invalid") from None
    elapsed = max(0.0, ((instant or datetime.now(UTC)) - started).total_seconds())
    return max(0.0, 1200.0 - elapsed)


def execute_run(engine, settings, run_id):
    from app.models import AutomationRun
    with Session(engine) as check:
        automatic = check.get(AutomationRun, run_id) is not None
    if automatic:
        from app.automatic_worker import execute
        return execute(engine, settings, run_id)
    vault, memory = Vault(settings), Memory(settings)
    readers = Readers(vault, settings)
    deadline = 0.0
    with Session(engine) as s:
        readers.session = s
        run = s.get(Run, run_id)
        def checkpoint(stage=None):
            s.refresh(run)
            if run.stop_requested:
                raise DomainError("run_stopped")
            if settings.library_enabled:
                from app import references,library_config
                for src in s.exec(select(Source).where(Source.approved==True)):
                    if src.path.startswith('reference:') and src.path in selection(s,settings)['paths']:
                        approved=references.assert_ready(s,settings,src.path,True)
                        if src.version and src.version!=approved.approved_hash:raise DomainError('reference_capture_changed')
                    elif src.path in selection(s,settings)['paths'] and library_config.catalogue_only(src.path,library_config.current(s).model_dump()):
                        raise DomainError('reference_catalogue_only')
            if time.monotonic() >= deadline:
                raise DomainError("run_budget_exhausted")
            if stage:
                run.stage = stage
                s.add(run)
            beat = s.get(Heartbeat, 1) or Heartbeat()
            beat.at = now()
            s.add(beat)
            s.commit()
        try:
            # Direct callers, as well as the worker, persist the first start.
            # A resumed run must never replace an existing timestamp.
            if not run.started_at:
                run.started_at = now()
                s.add(run)
                s.commit()
            deadline = time.monotonic() + remaining_run_seconds(run.started_at)
            vault.before_request = checkpoint
            readers.affine.before_request = checkpoint
            memory.before_call = checkpoint
            checkpoint("capture")
            getattr(memory, "ready", lambda: None)()
            sources, versions = capture_sources(s, settings, readers)
            original_paths = [x.path for x in sources]
            if any(x.error for x in sources) or len(versions) != len(sources):
                raise DomainError("source_capture_incomplete")
            if settings.publish_enabled:
                from app.review import migrate_legacy, consume_review
                try:
                    migrate_legacy(s, settings, vault)
                    consume_review(s, vault)
                except DomainError as error:
                    if error.code in ('run_stopped', 'run_budget_exhausted'):
                        raise
                    from app.connections import health
                    health(s, 'silverbullet-review', 'unavailable', error.code)
            memory.configure(json.loads(Path(__file__).with_name("bank-policy.json").read_text()))
            feedback_heads = {fb.question_id: fb for fb in s.exec(select(Feedback).order_by(Feedback.created_at, Feedback.id)).all()}
            for fb in feedback_heads.values():
                register_feedback(s, fb)
            s.commit()
            sources, versions = current_versions(s, original_paths=original_paths)
            checkpoint("retain")
            for source in sources:
                version = versions[source.id]
                if version.state == "oversized":
                    continue
                if version.state != "complete":
                    if not version.operation_id:
                        version.operation_id = str(uuid4())
                        version.state = "submitted"
                        s.add(version)
                        s.commit()
                    # Replay uses the persisted client operation UUID.
                    op = memory.call("GET", "/operations/" + version.operation_id, missing=True)
                    if not op:
                        memory.retain(source.id, version.hash, "# " + source.title + "\n\n" + version.body,
                                      version.operation_id, source_link(vault, source),
                                      kind="feedback" if source.path.startswith("feedback:") else "original")
                    if op and op.get("status") in ("failed", "cancelled"):
                        version.state, version.error = "remote_failed", "remote_operation_failed"
                        s.add(version)
                        s.commit()
                        raise DomainError("remote_operation_failed")
                    try:
                        memory.wait(version.operation_id, deadline, checkpoint)
                    except DomainError as error:
                        if error.code == "remote_operation_failed":
                            version.state, version.error = "remote_failed", error.code
                            s.add(version)
                            s.commit()
                        raise
                    memory.verify(source, version)
                    version.state = source.state = "complete"
                    version.error = source.error = ""
                    s.add_all([version, source])
                    s.commit()
            if any(v.state != "complete" for v in versions.values()):
                raise DomainError("oversized_sources_pending")
            checkpoint("feedback")
            for fb in s.exec(select(Feedback).where(Feedback.state == "pending")).all():
                fb.state = "complete" if feedback_heads[fb.question_id].id == fb.id else "superseded"
                s.add(fb)
            s.commit()
            original_ids = {x.id for x in sources if source_eligible(x.path)}
            relevant = set()
            for q in s.exec(select(Question)):
                if any(e['source_id'] in original_ids for e in q.evidence):
                    relevant.add('feedback:' + q.id)
            for f in s.exec(select(Finding)):
                if any(e['source_id'] in original_ids for e in f.evidence):
                    relevant.add('feedback:finding:' + f.id)
            selected_feedback, feedback_size = [], 0
            for x in sorted((x for x in sources if x.path in relevant), key=lambda x: x.captured_at, reverse=True):
                if feedback_size + len(versions[x.id].body) <= 12000:
                    selected_feedback.append(x)
                    feedback_size += len(versions[x.id].body)
            selected_ids = original_ids | {x.id for x in selected_feedback}
            sources = [x for x in sources if x.id in selected_ids]
            versions = {x.id: versions[x.id] for x in sources}
            fingerprint = digest(json.dumps([(x.id, versions[x.id].hash) for x in sources]))
            cached = s.get(Artifact, "review:" + fingerprint)
            if not cached:
                checkpoint("consolidate")
                consolidation = s.get(Artifact, "consolidate:" + fingerprint)
                if consolidation is None:
                    consolidation = Artifact(key="consolidate:" + fingerprint, value={"state": "submitting"})
                    s.add(consolidation)
                    s.commit()
                    result = memory.call("POST", "/consolidate", {})
                    consolidation.value = {"state": "submitted", "operation_id": result["operation_id"]}
                    s.add(consolidation)
                    s.commit()
                if not consolidation.value.get("operation_id"):
                    raise DomainError("consolidation_requires_reconciliation")
                memory.wait(consolidation.value["operation_id"], deadline, checkpoint)
                checkpoint("draft")
                from app.models import IntakeSection
                documents = {}
                for source in sources:
                    parts = s.exec(select(IntakeSection).where(IntakeSection.source_id == source.id,
                        IntakeSection.version == source.version, IntakeSection.state == 'reviewed')).all()
                    if parts:
                        documents[source.id] = sorted({p.document_id for p in parts})
                        provenance = {}
                        for part in parts:
                            original_part = s.get(IntakeSection, part.reused_from) if part.reused_from else part
                            if original_part is None:
                                raise DomainError('alias_provenance_missing')
                            provenance[part.document_id] = {'source_id': original_part.source_id, 'version': original_part.version}
                        object.__setattr__(source, 'document_provenance', provenance)
                trusted = memory.provenance(sources, documents) if documents else memory.provenance(sources)
                for original in sources:
                    object.__setattr__(original, 'evidence_family', evidence_family(s, original))
                items = draft(settings, sources, versions, trusted)
                cached = Artifact(key="review:" + fingerprint, value={"items": items})
                s.add(cached)
                s.commit()
            store_review(s, cached.value["items"], fingerprint)
            checkpoint("publish")
            from app.review import publish_review
            try:
                publish_review(s, settings, vault)
            except DomainError as error:
                if error.code in ('run_stopped', 'run_budget_exhausted'):
                    raise
                from app.connections import health
                health(s, 'silverbullet-review', 'unavailable', error.code)
            run.state, run.stage, run.error = "completed", "complete", ""
            run.result = {"sources": len(sources), "publication": s.get(Publication, 1).state}
            event(s, "run_completed", run.id)
        except DomainError as e:
            s.rollback()
            run = s.get(Run, run_id)
            run.state = "stopped" if e.code == "run_stopped" else "failed"
            run.error = e.code
            event(s, "run_failed", run.id + ": " + e.code)
        except Exception:
            s.rollback()
            run = s.get(Run, run_id)
            run.state, run.error = "failed", "internal_run_error"
            event(s, "run_failed", run.id + ": internal_run_error")
        finally:
            run.finished_at = now()
            s.add(run)
            s.commit()
            readers.close()
            vault.close()
            memory.close()


def due_schedule(s, settings, instant=None):
    schedule = s.get(Schedule, 1)
    if not schedule.enabled or not settings.acceptance_passed:
        return None
    local = (instant or datetime.now(UTC)).astimezone(ZoneInfo(schedule.timezone))
    due = local.replace(hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0)
    if local < due:
        due -= timedelta(days=1)
    key = due.isoformat()
    if key <= schedule.last_due:
        return None
    from app.automation import policy, budget
    p = policy(s)
    if p.mode == 'automatic' and (p.paused or budget(s, p)['seconds_remaining'] <= 0):
        schedule.last_due = key
        s.add(schedule); s.commit()
        return None
    job = enqueue(s, "schedule:" + key)
    if job.key == "schedule:" + key:
        schedule.last_due = key
        s.add(schedule)
        s.commit()
    return job
