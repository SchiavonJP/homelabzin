"""Owner-approved scopes, durable work and shared local-day quotas.

Reading the policy/status never initializes or changes it. Only owner actions
approve a scope. Discovery is metadata-only; bodies are read by the budgeted worker.
"""
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlmodel import select

from app.models import (Artifact, AutomationPolicy, AutomationRun, DailyUsage, Event,
                        IntakeNote, IntakeSection, Run, Schedule, Source, Version, now)
from app.vault import DomainError, digest, eligible, source_path

SECTION_SIZE = 12000
ZONE = ZoneInfo('America/Sao_Paulo')


def instant():
    return datetime.now(UTC)


def day_key(at=None):
    return (at or instant()).astimezone(ZONE).date().isoformat()


def lock(s):
    if s.bind.dialect.name == 'postgresql':
        s.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 1481855590})


def policy(s):
    p = s.get(AutomationPolicy, 1) or AutomationPolicy()
    from app.connections import scopes
    object.__setattr__(p, 'connections', scopes(s))
    return p


def scope_entry(value, folder=False):
    # Scope entries are literal vault-relative paths, never URLs/globs.
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise DomainError('invalid_scope_path', 422)
    clean = value.rstrip('/') if value != 'space/' else 'space'
    if clean == 'space':
        if folder:
            return 'space/'
        raise DomainError('invalid_scope_path', 422)
    if not clean.startswith('space/') or '\\' in clean or any(ord(x) < 32 for x in clean):
        raise DomainError('invalid_scope_path', 422)
    if any(x in ('', '.', '..') or x.startswith('.') for x in clean.split('/')):
        raise DomainError('invalid_scope_path', 422)
    if folder or value.endswith('/'):
        # Reuse mandatory exclusions by validating a hypothetical child note.
        if not eligible(clean + '/scope-check.md'):
            raise DomainError('ineligible_scope_path', 422)
        return clean + '/'
    if not eligible(clean):
        raise DomainError('ineligible_scope_path', 422)
    return clean


def normalized(folders, exclusions):
    return (sorted(set(scope_entry(x, True) for x in folders)),
            sorted(set(scope_entry(x, x.endswith('/')) for x in exclusions)))


def provider_of(path):
    return 'references' if path.startswith('reference:') else 'affine' if path.startswith('affine:') else 'silverbullet'


def in_scope(path, p):
    library = getattr(p, 'connections', {}).get('library', {})
    if path.startswith('reference:'):
        return not library.get('paused', True) and path in library.get('ready_paths', [])
    from app.library_config import catalogue_only
    if catalogue_only(path, library.get('catalogue', {})):
        return False
    if path.startswith('affine:'):
        from app.connections import in_affine_scope
        return in_affine_scope(path, getattr(p, 'connections', {}))
    return (eligible(path) and any(path.startswith(x) for x in p.folders)
            and not any(path.startswith(x) if x.endswith('/') else path == x for x in p.exclusions))


def preview(vault, folders, exclusions):
    folders, exclusions = normalized(folders, exclusions)
    p = AutomationPolicy(folders=folders, exclusions=exclusions)
    rows = vault.inventory()
    folder_set = set()
    for row in rows:
        parts = row['path'].split('/')[:-1]
        folder_set.update('/'.join(parts[:i]) + '/' for i in range(1, len(parts) + 1))
    return {'folders': sorted(folder_set), 'eligible': len(rows),
            'included': sum(in_scope(x['path'], p) for x in rows),
            'excluded': sum(not in_scope(x['path'], p) for x in rows),
            'paths': [x['path'] for x in rows if in_scope(x['path'], p)]}


def save_policy(s, mode, folders, exclusions, notes_per_day, minutes_per_day, expected_revision):
    folders, exclusions = normalized(folders, exclusions)
    if mode not in ('manual', 'automatic') or not 1 <= notes_per_day <= 10 or not 1 <= minutes_per_day <= 20:
        raise DomainError('invalid_automation_policy', 422)
    if mode == 'automatic' and not folders and not any(x.get('approved_at') for x in getattr(policy(s), 'connections', {}).values()):
        raise DomainError('automation_scope_required', 422)
    lock(s)
    p = policy(s)
    if p.revision != expected_revision:
        raise DomainError('automation_revision_conflict')
    if s.exec(select(Run).where(Run.state.in_(['queued', 'running']))).first():
        raise DomainError('automation_run_active')
    p.mode, p.folders, p.exclusions = mode, folders, exclusions
    p.notes_per_day, p.minutes_per_day = notes_per_day, minutes_per_day
    # Every save requires explicit activation; it never silently launches work.
    p.paused, p.revision, p.approved_at = True, p.revision + 1, now()
    s.add(p)
    s.add(Event(kind='automation_policy_saved', detail='revision=' + str(p.revision)))
    s.commit(); s.refresh(p)
    return p.model_dump()


def budget(s, p, at=None):
    day = day_key(at)
    usage = s.get(DailyUsage, day) or DailyUsage(day=day)
    active_seconds = 0.0
    for assignment in s.exec(select(AutomationRun).where(AutomationRun.day == day, AutomationRun.accounted == False)):
        run = s.get(Run, assignment.run_id)
        if run and run.started_at:
            elapsed = max(0, ((at or instant()) - datetime.fromisoformat(run.started_at)).total_seconds())
            active_seconds += min(assignment.limit_seconds, elapsed)
    seconds = usage.seconds + active_seconds
    tomorrow = datetime.fromisoformat(day).replace(tzinfo=ZONE) + timedelta(days=1)
    return {'day': day, 'notes_used': len(usage.notes), 'notes_limit': p.notes_per_day,
            'seconds_used': round(seconds, 3), 'seconds_limit': p.minutes_per_day * 60,
            'seconds_remaining': max(0, p.minutes_per_day * 60 - seconds),
            'resets_at': tomorrow.isoformat()}


def summary(s, detail=False):
    p = policy(s)
    counts = Counter()
    sections = Counter()
    for note in s.exec(select(IntakeNote)):
        counts[note.state if in_scope(note.path, p) else 'excluded'] += 1
    sources = {x.id: x for x in s.exec(select(Source))}
    for unit in s.exec(select(IntakeSection)):
        source = sources.get(unit.source_id)
        if source and source.version == unit.version and (unit.kind == 'feedback' or in_scope(source.path, p)):
            sections[unit.state] += 1
    from app.models import Question, Finding
    from sqlalchemy import func
    question_counts = dict(s.exec(select(Question.state, func.count()).group_by(Question.state)).all())
    waiting = len(s.exec(select(Question).where(Question.state == 'queued')).all())
    proposed = len(s.exec(select(Finding).where(Finding.state == 'proposed')).all())
    schedule = s.get(Schedule, 1)
    next_run = None
    if p.mode == 'automatic' and not p.paused and schedule and schedule.enabled:
        local = instant().astimezone(ZoneInfo(schedule.timezone))
        due = local.replace(hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0)
        next_run = (due if due > local else due + timedelta(days=1)).isoformat()
    result = {'approved_providers': [key for key, value in getattr(p, 'connections', {}).items() if value.get('approved_at')], 'next_run_at': next_run, 'policy': p.model_dump(), 'budget': budget(s, p), 'progress': dict(counts),
              'sections': dict(sections), 'question_counts': question_counts, 'queued_questions': waiting, 'proposed_findings': proposed,
              'last_activity': max((x.worked_at for x in s.exec(select(IntakeNote))), default='')}
    if not detail:
        result.pop('policy')
        result.update({'mode': p.mode, 'paused': p.paused})
    return result


def pause(s, expected_revision):
    lock(s)
    p = policy(s)
    if p.paused:
        return summary(s, True)
    if p.revision != expected_revision:
        raise DomainError('automation_revision_conflict')
    p.paused, p.revision = True, p.revision + 1
    s.add(p)
    for run in s.exec(select(Run).where(Run.state.in_(['queued', 'running']))):
        if s.get(AutomationRun, run.id):
            run.stop_requested = True
            if run.state == 'queued':
                run.state, run.error, run.finished_at = 'stopped', 'automation_paused', now()
            s.add(run)
    s.add(Event(kind='automation_paused', detail='revision=' + str(p.revision)))
    s.commit()
    return summary(s, True)


def resume(s, settings, expected_revision, key):
    lock(s)
    artifact_key = 'automation-resume:' + key
    previous = s.get(Artifact, artifact_key)
    if previous:
        return previous.value
    p = policy(s)
    if p.revision != expected_revision:
        raise DomainError('automation_revision_conflict')
    if p.mode != 'automatic' or not p.approved_at or (not p.folders and not any(x.get('approved_at') for x in getattr(p, 'connections', {}).values())):
        raise DomainError('automation_scope_required')
    if not settings.acceptance_passed:
        raise DomainError('acceptance_gates_pending')
    if s.exec(select(Run).where(Run.state.in_(['queued', 'running']))).first():
        raise DomainError('automation_run_active')
    p.paused, p.revision = False, p.revision + 1
    s.add(p); s.flush()
    available = budget(s, p)
    if available['seconds_remaining'] <= 0:
        response = {'state': 'waiting_budget', 'run_id': None, 'revision': p.revision}
        s.commit()
    else:
        from app.services import enqueue
        run = enqueue(s, key)
        response = {'state': 'queued', 'run_id': run.id, 'revision': p.revision}
    s.add(Artifact(key=artifact_key, value=response)); s.commit()
    return response


def attach(s, run):
    p = policy(s)
    if p.mode != 'automatic':
        return
    if p.paused:
        raise DomainError('automation_paused')
    if not p.approved_at or (not p.folders and not any(x.get('approved_at') for x in getattr(p, 'connections', {}).values())):
        raise DomainError('automation_scope_required')
    if budget(s, p)['seconds_remaining'] <= 0:
        raise DomainError('automation_daily_budget_exhausted')
    s.add(AutomationRun(run_id=run.id, policy={**p.model_dump(), 'connections': getattr(p, 'connections', {})}))


def begin_run(s, run, assignment, at=None):
    if assignment.day:
        return
    assignment.day = day_key(at or datetime.fromisoformat(run.started_at))
    usage = s.get(DailyUsage, assignment.day) or DailyUsage(day=assignment.day)
    assignment.limit_seconds = max(0, assignment.policy['minutes_per_day'] * 60 - usage.seconds)
    s.add_all([usage, assignment]); s.commit()


def charge_run(s, run, assignment, at=None):
    if assignment.accounted:
        return
    usage = s.get(DailyUsage, assignment.day) or DailyUsage(day=assignment.day)
    elapsed = max(0, ((at or instant()) - datetime.fromisoformat(run.started_at)).total_seconds())
    assignment.charged_seconds = min(assignment.limit_seconds, elapsed)
    assignment.accounted = True
    usage.seconds += assignment.charged_seconds
    s.add_all([usage, assignment]); s.commit()


def reserve_note(s, assignment, path, version):
    usage = s.get(DailyUsage, assignment.day)
    key = digest(path + '\n' + version)
    if key in usage.notes:
        return True
    if len(usage.notes) >= assignment.policy['notes_per_day']:
        return False
    usage.notes = [*usage.notes, key]
    s.add(usage); s.commit()
    return True


def section_ranges(body):
    start = 0
    while start < len(body):
        end = min(start + SECTION_SIZE, len(body))
        if end < len(body):
            split = body.rfind('\n\n', start + SECTION_SIZE // 2, end)
            if split < 0:
                split = body.rfind('\n', start + SECTION_SIZE // 2, end)
            if split >= 0:
                end = split + 1
        yield start, end
        start = end


def ensure_sections(s, source, version, kind='original', legacy_complete=False):
    existing = s.exec(select(IntakeSection).where(IntakeSection.source_id == source.id,
                                                IntakeSection.version == version.hash)).all()
    if existing:
        return existing
    # Legacy complete versions are already qualified; don't re-ingest them.
    for number, (start, end) in enumerate(section_ranges(version.body)):
        unit = IntakeSection(id=str(uuid5(NAMESPACE_URL, source.id + ':' + version.hash + ':' + str(number))),
            source_id=source.id, version=version.hash, number=number, start=start, end=end, kind=kind,
            state='reviewed' if legacy_complete else 'pending',
            document_id=source.id if legacy_complete else str(uuid5(NAMESPACE_URL, source.id + ':' + version.hash + ':' + str(number))))
        s.add(unit)
    s.commit()
    return s.exec(select(IntakeSection).where(IntakeSection.source_id == source.id,
                                            IntakeSection.version == version.hash).order_by(IntakeSection.number)).all()


def discover(s, p, inventory, providers=None):
    current = {row['path']: row for row in inventory}
    for row in inventory:
        path = row['path']
        if not in_scope(path, p):
            continue
        note = s.get(IntakeNote, path) or IntakeNote(path=path)
        hint = {'size': row.get('size', 0), 'lastModified': row.get('lastModified'), **({'title': row['title']} if 'title' in row else {})}
        if (note.state in ('excluded', 'missing') and note.error != 'generated_source_excluded') or note.inventory != hint or (not note.verified_at and note.state not in ('failed', 'excluded')):
            note.state = 'changed' if note.version else 'unread'
            note.next_attempt_at = '' if note.inventory != hint else note.next_attempt_at
        elif note.state == 'processed' and instant() - datetime.fromisoformat(note.verified_at) >= timedelta(days=7):
            note.state = 'audit'
        note.inventory = hint
        s.add(note)
    for note in s.exec(select(IntakeNote)):
        if not in_scope(note.path, p):
            note.state = 'excluded'
        elif note.path not in current and (providers is None or provider_of(note.path) in providers):
            note.state, note.error = 'missing', 'source_missing_no_automatic_deletion'
            source = s.get(Source, note.source_id) if note.source_id else None
            if source:
                source.state, source.error = 'unavailable', note.error
                s.add(source)
        s.add(note)
    s.commit()


def queue(s, p, offset=0, limit=30):
    rows = list(s.exec(select(IntakeNote).order_by(IntakeNote.discovered_at, IntakeNote.path)))
    sources = {x.id: x for x in s.exec(select(Source))}
    counts = Counter((x.source_id, x.version) for x in s.exec(select(IntakeSection)))
    completed = Counter((x.source_id, x.version) for x in s.exec(select(IntakeSection).where(IntakeSection.state == 'reviewed')))
    notes = [{**x.model_dump(), 'title': sources[x.source_id].title if x.source_id in sources else x.inventory.get('title') or ('Documento AFFiNE sem título' if x.path.startswith('affine:') else x.path), 'state': x.state if in_scope(x.path, p) else 'excluded',
              'sections_total': counts[(x.source_id, x.version)], 'sections_done': completed[(x.source_id, x.version)]}
             for x in rows]
    return {'notes': notes[offset:offset + limit], 'total': len(notes), 'offset': offset, 'limit': limit}
