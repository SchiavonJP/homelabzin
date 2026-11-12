"""Budgeted automatic intake. Imported only by the existing serialized worker."""
import json
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlmodel import Session, select

from app import automation as auto
from app.connections import Readers, family, evidence_family, relate, health, identity, permalink
from app.memory import Memory, draft
from app.models import (Artifact, AutomationPolicy, AutomationRun, DailyUsage, Event, Feedback,
                        Finding, Heartbeat, IntakeNote, IntakeSection, Question, Run, Source, Version, now)
from app.services import register_feedback, save_private, save_captured_snapshot, source_link, store_review
from app.vault import DomainError, Vault, digest, MAX_CAPTURE

CONTROL = {'automation_paused', 'run_stopped', 'automation_budget_exhausted', 'provider_paused',
           'reference_readiness_required','reference_readiness_revoked','reference_capture_changed','reference_catalogue_only'}
SHARED = ('hindsight_', 'gateway_')
PROVIDER_ERRORS = ('silverbullet_', 'affine_reader_unavailable', 'affine_reauth_required', 'affine_codec_version_mismatch', 'affine_workspace_not_configured')


def version_of(s, source_id, hashed):
    return s.exec(select(Version).where(Version.source_id == source_id, Version.hash == hashed)).one()


def views(s, units):
    sources, versions, documents = [], {}, {}
    for unit in units:
        source = s.get(Source, unit.source_id)
        original = version_of(s, unit.source_id, unit.version)
        proxy = SimpleNamespace(id=unit.id, parent_id=source.id, path=source.path,
            title=(original.title or source.title) + (' — seção ' + str(unit.number + 1) if len(original.body) > auto.SECTION_SIZE else ''),
            version=unit.version, family_id=evidence_family(s, source))
        if unit.reused_from:
            original_unit = s.get(IntakeSection, unit.reused_from)
            if not original_unit:
                raise DomainError('alias_provenance_missing')
            proxy.provenance_source_id, proxy.provenance_version = original_unit.source_id, original_unit.version
        sources.append(proxy)
        versions[unit.id] = SimpleNamespace(hash=unit.version, body=original.body[unit.start:unit.end])
        documents[unit.id] = [unit.document_id]
    return sources, versions, documents


def prepare_note(s, settings, note, vault, assignment):
    if isinstance(note.inventory.get('size'), (int, float)) and note.inventory['size'] > MAX_CAPTURE:
        raise DomainError('capture_too_large', 422)
    capture = vault.capture(note.path)
    if re.search(r'^generated:\s*true\s*$', capture.body[:1000], re.M):
        note.state, note.error = 'excluded', 'generated_source_excluded'
        note.verified_at = now(); s.add(note); s.commit()
        return []
    source = s.exec(select(Source).where(Source.path == note.path)).first()
    if not source:
        source = Source(path=note.path, title=getattr(capture, 'title', '') or Path(note.path).stem, approved=True)
        s.add(source); s.commit(); s.refresh(source)
    if note.path.startswith('affine:'):
        workspace, doc = identity(note.path)
        source.provider, source.connection_id = 'affine', 'affine'
        source.external_id, source.permalink = workspace + '/' + doc, permalink(note.path)
        source.title = capture.title
    if note.path.startswith('reference:'):
        source.provider,source.connection_id,source.external_id='references','library',note.path
        source.permalink=vault.permalink(note.path)
        source.title=capture.title
    relate(s, source, capture.body, settings)
    version = s.exec(select(Version).where(Version.source_id == source.id, Version.hash == capture.hash)).first()
    existing_complete = bool(version and version.state == 'complete')
    if not existing_complete and not auto.reserve_note(s, assignment, note.path, capture.hash):
        return None
    if not version:
        version = Version(source_id=source.id, hash=capture.hash, body=capture.body, etag=capture.etag, title=source.title)
        s.add(version)
        save_private(settings.state_path / 'captures' / source.id / (capture.hash + '.md'), capture.body)
    save_captured_snapshot(settings, source, version, capture)
    source.approved = True
    source.version, source.checked_at, source.captured_at = capture.hash, now(), version.captured_at
    source.error = ''
    note.source_id, note.version, note.verified_at = source.id, capture.hash, now()
    units = auto.ensure_sections(s, source, version, legacy_complete=existing_complete)
    reuse_extraction(s, source, version, units)
    note.state = 'processed' if all(x.state == 'reviewed' for x in units) else 'partial'
    source.state = 'complete' if note.state == 'processed' else 'partial'
    note.error, note.attempts, note.next_attempt_at = '', 0, ''
    s.add_all([source, version, note]); s.commit()
    return units



def reuse_extraction(s, source, version, units):
    if family(source) == source.id:
        return
    for other in s.exec(select(Source).where(Source.id != source.id)):
        if family(other) != family(source) or other.title != source.title or other.state != 'complete':
            continue
        original = s.exec(select(Version).where(Version.source_id == other.id, Version.hash == other.version)).first()
        if not original or original.state != 'complete' or original.body != version.body:
            continue
        previous = auto.ensure_sections(s, other, original, legacy_complete=True)
        if len(previous) != len(units) or any(x.state != 'reviewed' or x.document_id == other.id for x in previous):
            continue
        for unit, old in zip(units, previous):
            if unit.state == 'pending' and not unit.operation_id and (unit.start, unit.end) == (old.start, old.end):
                unit.reused_from, unit.document_id, unit.state = old.reused_from or old.id, old.document_id, 'retained'
                s.add(unit)
        return


def feedback_units(s):
    heads = {fb.question_id: fb for fb in s.exec(select(Feedback).order_by(Feedback.created_at, Feedback.id))}
    for fb in heads.values():
        source = register_feedback(s, fb)
        if source is None:
            continue
        # Carry authority metadata in every section title, including later parts.
        source.title = 'Resposta do proprietário (' + fb.disposition + ')'
        s.add(source); s.commit()
        version = version_of(s, source.id, source.version)
        auto.ensure_sections(s, source, version, 'feedback', legacy_complete=version.state == 'complete')
    return heads


def ready_units(s, p, kind):
    sources = {x.id: x for x in s.exec(select(Source))}
    result = []
    for unit in s.exec(select(IntakeSection).where(IntakeSection.kind == kind).order_by(IntakeSection.number, IntakeSection.id)):
        source = sources.get(unit.source_id)
        if not source or source.version != unit.version or (kind == 'original' and not auto.in_scope(source.path, p)):
            continue
        if unit.state in ('reviewed', 'held') or unit.next_attempt_at > now():
            continue
        result.append(unit)
    return result


def next_batch(s, settings, p, vault, assignment, checkpoint):
    # Persisted batches preserve consolidation/draft identity across process death.
    for record in s.exec(select(Artifact).where(Artifact.key.startswith('automatic-review:'))):
        if record.value.get('state') != 'pending':
            continue
        units = [s.get(IntakeSection, key) for key in record.value['primary']]
        if units and not all(u and u.state == 'reviewed' for u in units) and all(u and u.state != 'held' and u.next_attempt_at <= now() and s.get(Source, u.source_id).version == u.version and
               (u.kind == 'feedback' or (auto.in_scope(s.get(Source, u.source_id).path, p) and auto.in_scope(s.get(Source, u.source_id).path, auto.policy(s)))) for u in units):
            for unit in units:
                if unit.kind == 'original' and not auto.reserve_note(s, assignment, s.get(Source, unit.source_id).path, unit.version):
                    return []
            return units
    feedback = ready_units(s, p, 'feedback')
    if feedback:
        return feedback[:3]
    notes = list(s.exec(select(IntakeNote).order_by(IntakeNote.worked_at, IntakeNote.discovered_at, IntakeNote.path)))
    # Stable round-robin across available providers, oldest work within each.
    groups = {name: [n for n in notes if auto.provider_of(n.path) == name]
              for name in sorted(getattr(vault, 'available', {'silverbullet'}))}
    cursor = s.get(Artifact, 'provider-turn')
    order = list(groups)
    if cursor and cursor.value.get('last') in order:
        at = order.index(cursor.value['last']) + 1
        order = order[at:] + order[:at]
    notes = []
    while any(groups.values()):
        for name in order:
            if groups[name]:
                notes.append(groups[name].pop(0))
    batch = []
    for note in notes:
        checkpoint('capture')
        if auto.provider_of(note.path) not in getattr(vault, 'available', {'silverbullet'}):
            continue
        if (note.path.startswith('affine:') and not auto.in_scope(note.path, auto.policy(s))):
            continue
        if not auto.in_scope(note.path, p) or note.state not in ('unread', 'changed', 'audit', 'partial', 'failed') or note.next_attempt_at > now():
            continue
        usage = s.get(DailyUsage, assignment.day)
        known_key = digest(note.path + '\n' + note.version) if note.version else ''
        if len(usage.notes) >= p.notes_per_day and known_key not in usage.notes:
            continue
        try:
            if note.state in ('unread', 'changed', 'audit', 'failed'):
                prepared = prepare_note(s, settings, note, vault, assignment)
                if prepared is None:
                    continue
            else:
                if not auto.reserve_note(s, assignment, note.path, note.version):
                    continue
            candidates = [u for u in ready_units(s, p, 'original') if u.source_id == note.source_id]
            if candidates:
                batch.append(candidates[0])
                note.worked_at = now(); s.add(note)
                turn = s.get(Artifact, 'provider-turn') or Artifact(key='provider-turn')
                turn.value = {'last': auto.provider_of(note.path)}
                s.add(turn); s.commit()
        except DomainError as error:
            if error.code in CONTROL:
                raise
            if error.code.startswith(SHARED):
                raise
            if error.code in ('generated_source_excluded','reference_catalogue_only'):
                note.state, note.error = 'excluded', error.code
                s.add(note); s.commit()
                continue
            if error.code.startswith(PROVIDER_ERRORS):
                provider = auto.provider_of(note.path)
                health(s, provider, 'reauth_required' if error.code == 'affine_reauth_required' else 'unavailable', error.code)
                if hasattr(vault, 'available'):
                    vault.available.discard(provider)
                continue
            # A failed read consumes one attempt slot, without losing prior captures.
            auto.reserve_note(s, assignment, note.path, 'capture:' + digest(json.dumps(note.inventory, sort_keys=True)))
            note.attempts += 1
            if note.source_id:
                previous = s.get(Source, note.source_id)
                if previous:
                    previous.state, previous.error = 'unavailable', error.code
                    s.add(previous)
            note.state, note.error = 'failed', error.code
            note.next_attempt_at = (auto.instant() + timedelta(days=min(7, 2 ** min(note.attempts - 1, 3)))).isoformat()
            note.worked_at = now(); s.add(note); s.commit()
        if len(batch) == 3:
            break
    return batch


def retain_section(s, memory, vault, unit, checkpoint, deadline):
    from app.review import source_permalink
    sources, versions, _ = views(s, [unit])
    source, version = sources[0], versions[unit.id]
    if unit.state == 'retained':
        return
    checkpoint('retain')
    if source.path.startswith('affine:') and not auto.in_scope(source.path, auto.policy(s)):
        raise DomainError('provider_paused')
    created = not unit.operation_id
    if created:
        unit.operation_id, unit.state = str(uuid4()), 'submitting'
        s.add(unit); s.commit()
    try:
        op = memory.call('GET', '/operations/' + unit.operation_id, missing=True)
    except DomainError as error:
        if created and error.code in CONTROL:
            unit.operation_id, unit.state = '', 'pending'
            s.add(unit); s.commit()
        raise
    if not op:
        if not created:
            unit.state, unit.error = 'held', 'operation_missing_requires_reconciliation'
            s.add(unit); s.commit()
            raise DomainError(unit.error)
        try:
            memory.retain(unit.document_id, unit.version, '# ' + source.title + '\n\n' + version.body,
                unit.operation_id, vault.permalink(source.path) if unit.kind == 'original' else source_permalink(s, vault, s.get(Source, unit.source_id)),
                kind=unit.kind, metadata={'source_id': unit.source_id, 'family_id': evidence_family(s, s.get(Source, unit.source_id)), 'section_id': unit.id, 'start': unit.start, 'end': unit.end})
        except DomainError as error:
            if error.code in CONTROL:
                # Memory's control callback runs before the HTTP POST begins.
                unit.operation_id, unit.state = '', 'pending'
                s.add(unit); s.commit()
                raise
            raise DomainError('retain_acknowledgement_requires_reconciliation') from None
    unit.state = 'submitted'; s.add(unit); s.commit()
    if op and op.get('status') in ('failed', 'cancelled'):
        raise DomainError('remote_operation_failed')
    memory.wait(unit.operation_id, deadline, checkpoint)
    doc = memory.call('GET', '/documents/' + unit.document_id)
    metadata = doc.get('document_metadata') or {}
    if (doc.get('original_text') != '# ' + source.title + '\n\n' + version.body
            or metadata.get('version') != unit.version or metadata.get('source_id') != unit.source_id
            or metadata.get('start') != str(unit.start) or metadata.get('end') != str(unit.end)):
        raise DomainError('remote_document_mismatch')
    unit.state, unit.error = 'retained', ''
    s.add(unit); s.commit()


def relevant_context(s, units):
    parents = {x.source_id for x in units}
    wanted = set()
    for question in s.exec(select(Question)):
        if any(e['source_id'] in parents for e in question.evidence):
            wanted.add('feedback:' + question.id)
    for finding in s.exec(select(Finding)):
        if any(e['source_id'] in parents for e in finding.evidence):
            wanted.add('feedback:finding:' + finding.id)
    sources = {x.id: x for x in s.exec(select(Source)) if x.path in wanted}
    context, size = [], 0
    for unit in s.exec(select(IntakeSection).where(IntakeSection.kind == 'feedback', IntakeSection.state == 'reviewed').order_by(IntakeSection.id)):
        source = sources.get(unit.source_id)
        if source and source.version == unit.version and size + unit.end - unit.start <= 12000:
            context.append(unit); size += unit.end - unit.start
    return context


def review_batch(s, settings, memory, units, checkpoint, deadline):
    if any(u.kind == 'original' and s.get(Source, u.source_id).path.startswith('affine:') and not auto.in_scope(s.get(Source, u.source_id).path, auto.policy(s)) for u in units):
        raise DomainError('provider_paused')
    context = [] if any(x.kind == 'feedback' for x in units) else relevant_context(s, units)
    all_units = [*units, *context]
    fingerprint = digest(json.dumps(sorted(x.id for x in all_units)))
    epochs = []
    for sid in sorted({x.source_id for x in all_units}):
        epoch = s.get(Artifact, 'source-provenance-revision:' + sid)
        if epoch:
            epochs.append([sid, epoch.value['revision']])
    if epochs:
        fingerprint = digest(json.dumps([fingerprint, epochs]))
    key = 'automatic-review:' + fingerprint
    record = s.get(Artifact, key)
    if record is None:
        record = Artifact(key=key, value={'state': 'pending', 'primary': [x.id for x in units]})
        s.add(record); s.commit()
    checkpoint('consolidate')
    consolidation = s.get(Artifact, 'automatic-consolidate:' + fingerprint)
    if consolidation is None or consolidation.value.get('state') == 'not_submitted':
        consolidation = consolidation or Artifact(key='automatic-consolidate:' + fingerprint)
        consolidation.value = {'state': 'submitting'}
        s.add(consolidation); s.commit()
        try:
            response = memory.call('POST', '/consolidate', {})
            if not isinstance(response.get('operation_id'), str) or not response['operation_id']:
                raise DomainError('consolidation_requires_reconciliation')
        except DomainError as error:
            if error.code in CONTROL:
                consolidation.value = {'state': 'not_submitted'}
                s.add(consolidation); s.commit()
                raise
            raise DomainError('consolidation_requires_reconciliation') from None
        consolidation.value = {'state': 'submitted', 'operation_id': response['operation_id']}
        s.add(consolidation); s.commit()
    if not consolidation.value.get('operation_id'):
        raise DomainError('consolidation_requires_reconciliation')
    memory.wait(consolidation.value['operation_id'], deadline, checkpoint)
    cached = s.get(Artifact, 'automatic-draft:' + fingerprint)
    if cached is None:
        checkpoint('draft')
        sources, versions, documents = views(s, all_units)
        trusted = memory.provenance(sources, documents, allow_empty=True)
        sources = [x for x in sources if x.id in trusted]
        items = draft(settings, sources, versions, trusted) if sources else []
        mapping = {u.id: u for u in all_units}
        for item in items:
            for evidence in item['evidence']:
                unit = mapping[evidence['source_id']]
                evidence.update({'source_id': unit.source_id, 'section_id': unit.id,
                                 'section_start': unit.start, 'section_end': unit.end})
            if item['kind'] == 'question':
                scope = sorted({evidence_family(s, s.get(Source, e['source_id'])) for e in item['evidence']})
                item['issue'] = 'auto:' + digest(json.dumps([scope, item['issue'].strip().casefold()]))
        cached = Artifact(key='automatic-draft:' + fingerprint, value={'items': items})
        s.add(cached); s.commit()
    checkpoint('draft')
    store_review(s, cached.value['items'], fingerprint)
    for unit in units:
        unit.state, unit.error = 'reviewed', ''
        s.add(unit)
    record.value = {**record.value, 'state': 'complete'}
    s.add(record)
    # Section completion, parent progress and review receipt commit together.
    for sid in {u.source_id for u in units}:
        source = s.get(Source, sid)
        version = version_of(s, sid, source.version)
        complete = all(u.state == 'reviewed' for u in s.exec(select(IntakeSection).where(
            IntakeSection.source_id == sid, IntakeSection.version == source.version)))
        if complete:
            source.state, source.error, version.state = 'complete', '', 'complete'
            s.add_all([source, version])
        note = s.get(IntakeNote, source.path)
        if note:
            note.state, note.error = ('processed' if complete else 'partial'), ''
            s.add(note)
    s.commit()


def fail_units(s, units, error):
    ids = {u.id for u in units}
    for record in s.exec(select(Artifact).where(Artifact.key.startswith('automatic-review:'))):
        if record.value.get('state') == 'pending' and ids.intersection(record.value['primary']):
            record.value = {**record.value, 'state': 'failed'}
            s.add(record)
    for unit in units:
        unit = s.get(IntakeSection, unit.id)
        unit.attempts += 1
        unit.error = error.code
        held = ('reconciliation' in error.code or error.code == 'remote_document_mismatch')
        unit.state = 'held' if held else 'failed'
        if error.code == 'remote_operation_failed':
            # A known terminal operation may be retried with a fresh identifier.
            unit.operation_id = ''
        unit.next_attempt_at = (auto.instant() + timedelta(days=min(7, 2 ** min(unit.attempts - 1, 3)))).isoformat()
        s.add(unit)
        source = s.get(Source, unit.source_id)
        note = s.get(IntakeNote, source.path)
        if note:
            note.state, note.error, note.next_attempt_at = 'failed', error.code, unit.next_attempt_at
            s.add(note)
    s.commit()


def execute(engine, settings, run_id):
    vault, memory = Vault(settings), Memory(settings)
    readers = Readers(vault, settings)
    with Session(engine) as s:
        readers.session = s
        run, assignment = s.get(Run, run_id), s.get(AutomationRun, run_id)
        p = AutomationPolicy(**assignment.policy)
        object.__setattr__(p, 'connections', assignment.policy.get('connections', {}))
        run.started_at = run.started_at or now()
        s.add(run); s.commit()
        auto.begin_run(s, run, assignment)
        elapsed = max(0, (auto.instant() - datetime.fromisoformat(run.started_at)).total_seconds())
        deadline = time.monotonic() + max(0, assignment.limit_seconds - elapsed)
        batches, processed = 0, 0
        active_units = []
        def checkpoint(stage=None):
            s.refresh(run)
            current = auto.policy(s); s.refresh(current) if current.id and s.get(AutomationPolicy, 1) else None
            if current.paused or run.stop_requested:
                raise DomainError('automation_paused' if current.paused else 'run_stopped')
            if any(u.kind == 'original' and s.get(Source, u.source_id).path.startswith('affine:') and not auto.in_scope(s.get(Source, u.source_id).path, current) for u in active_units):
                raise DomainError('provider_paused')
            if settings.library_enabled:
                from app import references,library_config
                for u in active_units:
                    if u.kind != 'original':continue
                    src=s.get(Source,u.source_id)
                    if src.path.startswith('reference:'):
                        approved=references.assert_ready(s,settings,src.path,True)
                        if approved.approved_hash!=u.version:raise DomainError('reference_capture_changed')
                    elif library_config.catalogue_only(src.path,library_config.current(s).model_dump()):
                        raise DomainError('reference_catalogue_only')
            if time.monotonic() >= deadline:
                raise DomainError('automation_budget_exhausted')
            if stage:
                run.stage = stage; s.add(run)
            beat = s.get(Heartbeat, 1) or Heartbeat()
            beat.at = now(); s.add(beat); s.commit()
        vault.before_request = checkpoint
        memory.before_call = checkpoint
        try:
            if not settings.acceptance_passed:
                raise DomainError('acceptance_gates_pending')
            checkpoint('capture')
            getattr(memory, 'ready', lambda: None)()
            rows, available = readers.scan(s, p, checkpoint)
            auto.discover(s, p, rows, available)
            if settings.publish_enabled:
                from app.review import migrate_legacy, consume_review
                try:
                    migrate_legacy(s, settings, vault)
                    consume_review(s, vault)
                except DomainError as error:
                    if error.code in CONTROL:
                        raise
                    health(s, 'silverbullet-review', 'unavailable', error.code)
            heads = feedback_units(s)
            configured = False
            while True:
                checkpoint()
                units = next_batch(s, settings, p, readers, assignment, checkpoint)
                if not units:
                    break
                if not configured:
                    memory.configure(json.loads(Path(__file__).with_name('bank-policy.json').read_text()))
                    configured = True
                active_units = units
                try:
                    for unit in units:
                        retain_section(s, memory, readers, unit, checkpoint, deadline)
                    review_batch(s, settings, memory, units, checkpoint, deadline)
                    batches += 1; processed += len(units)
                except DomainError as error:
                    if error.code == 'provider_paused':
                        continue
                    if error.code in CONTROL:
                        raise
                    fail_units(s, units, error)
                    if error.code.startswith(SHARED):
                        raise
                finally:
                    active_units = []
            enabled_providers = ({'silverbullet'} if p.folders else set()) | ({'references'} if settings.library_enabled else set()) | ({'affine'} if getattr(p, 'connections', {}).get('affine', {}).get('approved_at') and not getattr(p, 'connections', {}).get('affine', {}).get('paused', True) else set())
            if enabled_providers and not enabled_providers.intersection(readers.available) and not processed:
                raise DomainError('source_connections_unavailable', 503)
            checkpoint('publish')
            if settings.publish_enabled:
                from app.review import publish_review
                try:
                    publish_review(s, settings, vault)
                except DomainError as error:
                    if error.code in CONTROL:
                        raise
                    health(s, 'silverbullet-review', 'unavailable', error.code)
            for previous in s.exec(select(Feedback).where(Feedback.state == 'pending')):
                if heads[previous.question_id].id != previous.id:
                    previous.state = 'superseded'; s.add(previous)
            for fb in heads.values():
                source = s.exec(select(Source).where(Source.path == 'feedback:' + fb.question_id)).first()
                if fb.disposition == 'deferred' or (source and source.state == 'complete'):
                    fb.state = 'complete'; s.add(fb)
            run.state, run.stage, run.error = 'completed', 'complete', ''
        except DomainError as error:
            s.rollback(); run = s.get(Run, run_id)
            run.error = error.code
            run.state = 'stopped' if error.code in ('automation_paused', 'run_stopped') else 'completed' if error.code == 'automation_budget_exhausted' else 'failed'
        except Exception:
            s.rollback(); run = s.get(Run, run_id)
            run.state, run.error = 'failed', 'internal_run_error'
        finally:
            run.finished_at = now()
            run.result = {'mode': 'automatic', 'sections_processed': processed, 'batches': batches, 'available_providers': sorted(readers.available)}
            s.add(run)
            assignment = s.get(AutomationRun, run_id)
            auto.charge_run(s, run, assignment)
            from app.services import request_publication
            if processed:
                request_publication(s); s.commit()
            readers.close(); vault.close(); memory.close()
