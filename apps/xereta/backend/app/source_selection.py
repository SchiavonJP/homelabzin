"""Owner-selected intake batches; retained sources remain available as history."""
import re
from pathlib import PurePosixPath

from sqlalchemy import text
from sqlmodel import select

from app.models import Artifact, Event, Run, Source, now
from app.vault import DomainError
from app.connections import source_eligible as eligible

KEY = 'source-selection:v1'
LIMIT = 3


def selection(s, settings):
    item = s.get(Artifact, KEY)
    paths = list(item.value['paths']) if item else list(settings.pilot_paths[:LIMIT])
    if not 1 <= len(paths) <= LIMIT or len(set(paths)) != len(paths) or not all(eligible(p) for p in paths):
        raise DomainError('invalid_source_selection')
    known = [x.path for x in s.exec(select(Source).where(Source.approved == True)) if eligible(x.path)]
    approved = set(known) | set(paths) | set(item.value.get('approved_paths', []) if item else [])
    return {'paths': paths, 'approved_paths': sorted(approved),
            'revision': item.value['revision'] if item else 0, 'limit': LIMIT}


def catalogue(s, settings, vault):
    if hasattr(vault,'session'):vault.session=s
    current = selection(s, settings)
    inventory = {x['path']: x for x in vault.inventory()}
    retained = {x.path: x for x in s.exec(select(Source)) if eligible(x.path)}
    paths = sorted(set(inventory) | set(current['paths']) | set(current['approved_paths']))
    notes = []
    for path in paths:
        if not eligible(path):
            continue
        source = retained.get(path)
        notes.append({'path': path, 'title': source.title if source else inventory.get(path, {}).get('title') or PurePosixPath(path).stem,
                      'size': inventory.get(path, {}).get('size', 0), 'available': path in inventory,
                      'approved': path in current['approved_paths'], 'active': path in current['paths'],
                      'ingested': bool(source and source.version), 'version': source.version if source else '',
                      'state': source.state if source else 'not_ingested',
                      'captured_at': source.captured_at if source else '',
                      'provider': 'affine' if path.startswith('affine:') else 'silverbullet',
                      'permalink': vault.permalink(path)})
    return {'selection': current, 'notes': notes}


def choose(s, settings, vault, paths, expected_revision):
    from app.services import PILOT_LIMIT
    from app.automation import policy
    if policy(s).mode == 'automatic':
        raise DomainError('switch_to_manual_first')
    if not 1 <= len(paths) <= LIMIT or len(paths) != len(set(paths)) or not all(eligible(p) for p in paths):
        raise DomainError('invalid_source_selection', 422)
    # Serialize with enqueue so a running/queued job keeps a stable intake batch.
    if s.bind.dialect.name == 'postgresql':
        s.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 1481855590})
    current = selection(s, settings)
    if current['revision'] != expected_revision:
        raise DomainError('source_selection_revision_conflict')
    if s.exec(select(Run).where(Run.state.in_(['queued', 'running']))).first():
        raise DomainError('source_selection_run_active')
    if hasattr(vault,'session'):vault.session=s
    available = {x['path'] for x in vault.inventory()}
    for path in paths:
        if path not in available:
            raise DomainError('source_selection_note_missing', 422)
        captured = vault.capture(path)
        if len(captured.body) > PILOT_LIMIT:
            raise DomainError('source_selection_note_oversized', 422)
        if re.search(r'^generated:\s*true\s*$', captured.body[:1000], re.M):
            raise DomainError('generated_source_excluded', 422)
    value = {'paths': list(paths), 'approved_paths': sorted(set(current['approved_paths']) | set(paths)),
             'revision': current['revision'] + 1, 'updated_at': now()}
    item = s.get(Artifact, KEY) or Artifact(key=KEY)
    item.value = value
    s.add(item)
    s.add(Event(kind='source_selection_changed', detail='revision=' + str(value['revision']) + ';notes=' + str(len(paths))))
    s.commit()
    return {**value, 'limit': LIMIT}
