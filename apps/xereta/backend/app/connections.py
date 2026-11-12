"""Read-only source adapters. Credentials stay in server settings, never DB/API DTOs."""
import base64
import json
import re
from collections import Counter
from contextlib import closing
from urllib.parse import quote

import httpx
from sqlmodel import select

from app.models import (Artifact, IntakeNote, IntakeSection, Run, Source, SourceConnection,
                        SourceRelationship, Version, now)
from app.vault import Capture, DomainError, MAX_CAPTURE, digest, eligible

AFFINE = 'affine'
ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


def affine_path(workspace, document):
    if not ID.fullmatch(workspace) or not ID.fullmatch(document):
        raise DomainError('invalid_affine_identity', 422)
    return f'affine:main:{workspace}:{document}'


def identity(path):
    parts = path.split(':')
    if len(parts) != 4 or parts[:2] != ['affine', 'main']:
        raise DomainError('invalid_affine_identity', 422)
    affine_path(parts[2], parts[3])
    return parts[2], parts[3]


def source_eligible(path):
    if path.startswith('reference:'):
        from app.references import path_id
        try:
            path_id(path); return True
        except DomainError:
            return False
    if path.startswith('affine:'):
        try:
            identity(path)
            return True
        except DomainError:
            return False
    return eligible(path)


def permalink(path):
    workspace, doc = identity(path)
    return f'https://affine.joaopaulo.me/workspace/{workspace}/{doc}'


def scopes(s):
    from app.library_config import scope
    return {**{x.id: x.model_dump() for x in s.exec(select(SourceConnection))}, 'library': scope(s)}


def in_affine_scope(path, connections):
    try:
        workspace, document = identity(path)
    except DomainError:
        return False
    p = connections.get(AFFINE, {})
    return bool(p.get('approved_at') and not p.get('paused', True) and
                workspace == p.get('workspace') and document not in p.get('exclusions', []))


def health(s, provider, state, error=''):
    key = 'connection-health:' + provider
    item = s.get(Artifact, key) or Artifact(key=key)
    previous = item.value
    item.value = {'state': state, 'error': error, 'checked_at': now(),
                  'last_success_at': now() if state == 'healthy' else previous.get('last_success_at', '')}
    s.add(item); s.commit()


def statuses(s, settings):
    configs = scopes(s)
    return {'connections': [{'id': provider, 'provider': provider,
        'configured': provider == 'silverbullet' or bool(settings.affine_workspaces and settings.affine_reader_token.get_secret_value()),
        'workspaces': settings.affine_workspaces if provider == AFFINE else [],
        'scope': configs.get(provider, SourceConnection(id=provider, provider=provider).model_dump()),
        'health': s.get(Artifact, 'connection-health:' + provider).value if s.get(Artifact, 'connection-health:' + provider) else {'state': 'unchecked'},
        'progress': dict(Counter(x.state for x in s.exec(select(IntakeNote)) if not x.path.startswith('reference:') and x.path.startswith('affine:') == (provider == AFFINE)))}
        for provider in ('silverbullet', AFFINE)]}


class AffineReader:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.client = httpx.Client(base_url=settings.affine_reader_url, trust_env=False, follow_redirects=False,
            timeout=40, headers={'Authorization': 'Bearer ' + settings.affine_reader_token.get_secret_value()}, transport=transport)

    def close(self):
        self.client.close()

    def call(self, method, path, body=None):
        getattr(self, 'before_request', lambda: None)()
        try:
            with self.client.stream(method, path, json=body) as r:
                if r.status_code >= 300:
                    safe_error = ''
                    buffer = bytearray()
                    for part in r.iter_bytes():
                        buffer.extend(part)
                        if len(buffer) > 65536:
                            break
                    if len(buffer) <= 65536:
                        try:
                            envelope = json.loads(buffer)
                            code = envelope.get('error') if isinstance(envelope, dict) else ''
                            safe_error = {'codec_version_mismatch': 'affine_codec_version_mismatch',
                                'response_too_large': 'affine_capture_too_large',
                                'workspace_not_allowed': 'affine_workspace_not_configured'}.get(code, '')
                        except (ValueError, TypeError):
                            pass
                    raise DomainError('affine_reauth_required' if r.status_code in (401, 403) else
                                      'affine_document_missing' if r.status_code == 404 else safe_error or 'affine_reader_unavailable', 503)
                chunks, total = [], 0
                for chunk in r.iter_bytes():
                    total += len(chunk)
                    if total > MAX_CAPTURE * 3:
                        raise DomainError('affine_response_too_large', 503)
                    chunks.append(chunk)
            value = json.loads(b''.join(chunks))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except httpx.HTTPError:
            raise DomainError('affine_reader_unavailable', 503) from None
        except (ValueError, TypeError):
            raise DomainError('affine_invalid_response', 503) from None

    def page(self, workspace, cursor=None):
        if workspace not in self.settings.affine_workspaces:
            raise DomainError('affine_workspace_not_configured', 422)
        data = self.call('POST', '/inventory', {'workspace': workspace, 'after': cursor})
        items = data.get('items')
        if not isinstance(items, list) or len(items) > 100 or not isinstance(data.get('complete'), bool):
            raise DomainError('affine_invalid_inventory', 503)
        result = []
        for row in items:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not isinstance(row.get('updated_at'), (str, type(None))):
                raise DomainError('affine_invalid_inventory', 503)
            result.append({'path': affine_path(workspace, row['id']), 'title': str(row.get('title') or '')[:500],
                           'size': 0, 'lastModified': row.get('updated_at'), 'provider': AFFINE, 'permalink': permalink(affine_path(workspace, row['id']))})
        if not data['complete'] and (not isinstance(data.get('cursor'), str) or not data['cursor'] or data['cursor'] == cursor):
            raise DomainError('affine_invalid_cursor', 503)
        return result, data['complete'], data.get('cursor')

    def inventory(self, workspace):
        rows, cursor = [], None
        for _ in range(100):
            page, complete, cursor = self.page(workspace, cursor)
            rows.extend(page)
            if complete:
                return rows
        raise DomainError('affine_inventory_incomplete', 503)

    def capture(self, path):
        workspace, document = identity(path)
        if workspace not in self.settings.affine_workspaces:
            raise DomainError('affine_workspace_not_configured', 422)
        result = self.call('POST', '/capture', {'workspace': workspace, 'document': document})
        if result.get('complete') is not True:
            raise DomainError('generated_source_excluded' if result.get('reason') == 'generated_source_excluded' else 'affine_capture_incomplete', 422)
        try:
            title, body = result['title'], result['body']
            raw = base64.b64decode(result['snapshot'], validate=True)
            if (not isinstance(title, str) or len(title) > 500 or not isinstance(body, str)
                    or not body.strip() or len(body.encode()) > MAX_CAPTURE or len(raw) > MAX_CAPTURE
                    or digest(raw) != result['snapshot_sha256'] or digest(body) != result['markdown_sha256']):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise DomainError('affine_capture_integrity_failed', 503) from None
        body = body.replace('\r\n', '\n').replace('\r', '\n')
        captured = Capture(path, body, digest(title + '\n\0' + body), result['snapshot_sha256'])
        captured.title, captured.original_title, captured.snapshot, captured.warnings = title if title.strip() else 'Sem título', title, raw, result.get('warnings', [])
        return captured


class Readers:
    """Dispatch captured source reads; publishing continues to use the original Vault."""
    def __init__(self, vault, settings):
        self.vault, self.settings = vault, settings
        self.affine = AffineReader(settings)
        self.available = {'silverbullet'}
        self.session = None

    def close(self):
        self.affine.close()

    def capture(self, path):
        from app import references,library_config
        if path.startswith('reference:'):
            if self.session is None:raise DomainError('reference_session_required')
            return references.capture(self.session,self.settings,path)
        if self.settings.library_enabled and self.session is not None and library_config.catalogue_only(path,library_config.current(self.session).model_dump()):
            raise DomainError('reference_catalogue_only',422)
        captured=self.affine.capture(path) if path.startswith('affine:') else self.vault.capture(path)
        if self.settings.library_enabled and self.session is not None and references.catalogue_copy(self.session,path,captured.body):
            raise DomainError('reference_catalogue_only',422)
        return captured

    def permalink(self, path):
        if path.startswith('reference:'):
            from app.references import item_of,path_id
            return item_of(self.session,path_id(path)).url
        return permalink(path) if path.startswith('affine:') else self.vault.permalink(path)

    def inventory(self):
        rows = []
        if self.session is not None:
            from app.references import inventory
            rows.extend(inventory(self.session,self.settings))
        try:
            rows.extend(self.vault.inventory())
        except DomainError:
            pass
        for workspace in self.settings.affine_workspaces:
            try:
                with closing(AffineReader(self.settings)) as reader:
                    rows.extend(reader.inventory(workspace))
            except DomainError:
                continue
        return rows

    def scan(self, s, p, checkpoint):
        rows, successful = [], set()
        try:
            rows.extend(self.vault.inventory()); successful.add('silverbullet')
            health(s, 'silverbullet', 'healthy')
        except DomainError as error:
            if error.code in ('automation_paused', 'run_stopped', 'automation_budget_exhausted'):
                raise
            health(s, 'silverbullet', 'unavailable', error.code)
        config = getattr(p, 'connections', {}).get(AFFINE, {})
        if config.get('approved_at') and not config.get('paused', True):
            workspace = config['workspace']
            key = 'affine-inventory:' + workspace
            saved = s.get(Artifact, key) or Artifact(key=key, value={'rows': [], 'cursor': None})
            accumulated = {r['path']: r for r in saved.value.get('rows', [])}
            cursor = saved.value.get('cursor')
            self.affine.before_request = checkpoint
            try:
                for _ in range(100):
                    page, complete, next_cursor = self.affine.page(workspace, cursor)
                    accumulated.update({r['path']: r for r in page})
                    if complete:
                        rows.extend(accumulated.values()); successful.add(AFFINE)
                        saved.value = {'rows': [], 'cursor': None}; s.add(saved); s.commit()
                        health(s, AFFINE, 'healthy'); break
                    cursor = next_cursor
                    saved.value = {'rows': list(accumulated.values()), 'cursor': cursor}
                    s.add(saved); s.commit()
                else:
                    raise DomainError('affine_inventory_incomplete', 503)
            except DomainError as error:
                if error.code in ('automation_paused', 'run_stopped', 'automation_budget_exhausted'):
                    raise
                health(s, AFFINE, 'reauth_required' if error.code == 'affine_reauth_required' else 'unavailable', error.code)
        if self.settings.library_enabled:
            from app.references import inventory
            rows.extend(inventory(s,self.settings));successful.add('references')
        self.available = successful
        return rows, successful


def save_scope(s, settings, workspace, exclusions, expected_revision):
    from app.automation import lock
    if workspace not in settings.affine_workspaces or len(exclusions) > 10000 or any(not ID.fullmatch(x) for x in exclusions):
        raise DomainError('invalid_affine_scope', 422)
    lock(s)
    p = s.get(SourceConnection, AFFINE) or SourceConnection(id=AFFINE)
    if p.revision != expected_revision:
        raise DomainError('connection_revision_conflict')
    if s.exec(select(Run).where(Run.state.in_(['queued', 'running']))).first():
        raise DomainError('connection_run_active')
    p.workspace, p.exclusions = workspace, sorted(set(exclusions))
    p.approved_at, p.paused, p.revision = now(), True, p.revision + 1
    s.add(p); s.commit(); s.refresh(p)
    return p.model_dump()


def control(s, expected_revision, paused):
    from app.automation import lock
    lock(s)
    p = s.get(SourceConnection, AFFINE)
    if p is None or not p.approved_at:
        raise DomainError('affine_scope_required')
    if p.revision != expected_revision:
        raise DomainError('connection_revision_conflict')
    p.paused, p.revision = paused, p.revision + 1
    s.add(p); s.commit(); s.refresh(p)
    return p.model_dump()


def family(source):
    return source.family_id or source.id


def relate(s, source, body, settings):
    """Only verified mappings or exact text auto-link; title alone suggests."""
    s.info.pop('evidence_families', None)
    source.family_id = source.family_id or source.id
    if source.path.startswith('feedback:'):
        return
    overrides = list(s.exec(select(SourceRelationship).where(SourceRelationship.method == 'owner')))
    if any(x.source_id == source.id for x in overrides):
        s.add(source)
        return
    separated = {x.source_id for x in overrides if x.state == 'unlinked'}
    candidates = sorted(s.exec(select(Source).where(Source.id != source.id)).all(), key=lambda x: x.id)
    mapped_path = settings.affine_imports.get(source.external_id, '') if source.provider == AFFINE else ''
    if source.provider=='references':
        from app.references import item_of,path_id,primary_link
        item=item_of(s,path_id(source.path))
        for old in candidates:
            version=s.exec(select(Version).where(Version.source_id==old.id,Version.hash==old.version)).first()
            if version and '[[ReadItLater]]' in version.body[:500].replace('\\','') and primary_link(version.body)[0]==item.url:
                mapped_path=old.path;break
    candidates.sort(key=lambda x: (x.path != mapped_path, x.id))
    canonical = None
    exact_sources = set(s.exec(select(Version.source_id).where(Version.body == body).distinct()).all())
    for other in candidates:
        if other.id in separated or other.path.startswith('feedback:'):
            continue
        relationship = s.exec(select(SourceRelationship).where(SourceRelationship.source_id == source.id,
            SourceRelationship.target_id == other.id)).first()
        if relationship and relationship.state == 'unlinked':
            continue
        exact = other.id in exact_sources
        mapped = bool(mapped_path and other.path == mapped_path)
        if not (exact or mapped or (other.provider != source.provider and source.title != 'Sem título' and source.title == other.title)):
            continue
        relationship = relationship or SourceRelationship(source_id=source.id, target_id=other.id)
        if exact or mapped:
            # Prefer the existing family; do not change document IDs or old approvals.
            canonical = canonical or family(other)
            old_roots = {family(source), family(other)} - {canonical}
            for member in [source, *candidates]:
                if family(member) in old_roots:
                    member.family_id = canonical; s.add(member)
            source.family_id = canonical
            relationship.state, relationship.method = 'linked', 'verified-import' if mapped else 'exact-content'
        else:
            relationship.method = 'title'
        s.add(relationship)
    s.add(source)


def relationships(s):
    sources = {x.id: x for x in s.exec(select(Source))}
    result = []
    for row in s.exec(select(SourceRelationship)):
        if row.state == 'superseded':
            continue
        a, b = sources.get(row.source_id), sources.get(row.target_id)
        if not a or not b:
            continue
        av = s.exec(select(Version).where(Version.source_id == a.id, Version.hash == a.version)).first()
        bv = s.exec(select(Version).where(Version.source_id == b.id, Version.hash == b.version)).first()
        result.append({**row.model_dump(), 'source_title': a.title, 'target_title': b.title,
            'source_provider': a.provider, 'target_provider': b.provider,
            'source_url': permalink(a.path) if a.provider == AFFINE else 'https://silverbullet.joaopaulo.me/' + quote(a.path.removesuffix('.md'), safe='/'),
            'target_url': permalink(b.path) if b.provider == AFFINE else 'https://silverbullet.joaopaulo.me/' + quote(b.path.removesuffix('.md'), safe='/'),
            'diverged': bool(av and bv and av.body != bv.body), 'family_id': family(a)})
    return result


def change_relationship(s, rid, state, revision):
    from app.automation import lock
    lock(s)
    row = s.get(SourceRelationship, rid)
    if row is None or row.revision != revision:
        raise DomainError('relationship_revision_conflict')
    if s.exec(select(Run).where(Run.state.in_(['queued', 'running']))).first():
        raise DomainError('connection_run_active')
    if state not in ('linked', 'unlinked'):
        raise DomainError('invalid_relationship', 422)
    a, b = s.get(Source, row.source_id), s.get(Source, row.target_id)
    old = family(a)
    members = [source for source in s.exec(select(Source)) if family(source) == old]
    if state == 'linked':
        for related in s.exec(select(SourceRelationship)):
            if related.id != row.id and related.state == 'unlinked' and a.id in (related.source_id, related.target_id):
                related.state = 'superseded'; related.revision += 1; s.add(related)
        for source in members:
            source.family_id = family(b); s.add(source)
    else:
        remaining = [source for source in members if source.id != a.id]
        remaining_root = (b.id if any(x.id == b.id for x in remaining) else remaining[0].id) if remaining else ''
        for source in remaining:
            source.family_id = remaining_root; s.add(source)
        a.family_id = a.id; s.add(a)
        for related in s.exec(select(SourceRelationship)):
            if related.id != row.id and a.id in (related.source_id, related.target_id):
                related.state, related.method = 'unlinked', 'owner'
                related.revision += 1; s.add(related)
    row.state, row.method, row.revision = state, 'owner', row.revision + 1
    # Separating a reused copy requires its own extraction before fresh review.
    # Preserve the old provenance receipt; original captures and approvals stay.
    from app.services import request_publication
    archived = []
    for unit in s.exec(select(IntakeSection)):
        if not unit.reused_from:
            continue
        current_source = s.get(Source, unit.source_id)
        origin_unit = s.get(IntakeSection, unit.reused_from)
        origin_source = s.get(Source, origin_unit.source_id) if origin_unit else None
        if not current_source or current_source.version != unit.version or not origin_source or family(current_source) == family(origin_source):
            continue
        archived.append(unit.model_dump())
        unit.reused_from, unit.document_id, unit.operation_id = '', unit.id, ''
        unit.state, unit.error, unit.next_attempt_at = 'pending', '', ''
        s.add(unit)
        current_source.state, current_source.error = 'partial', 'source_relationship_changed_requires_retain'
        version = s.exec(select(Version).where(Version.source_id == current_source.id, Version.hash == unit.version)).one()
        version.state = 'pending'; s.add_all([current_source, version])
        note = s.get(IntakeNote, current_source.path)
        if note:
            note.state, note.error, note.next_attempt_at = 'partial', current_source.error, ''
            s.add(note)
        epoch_key = 'source-provenance-revision:' + current_source.id
        epoch = s.get(Artifact, epoch_key) or Artifact(key=epoch_key, value={'revision': 0})
        epoch.value = {'revision': epoch.value['revision'] + 1}
        s.add(epoch)
    if archived:
        s.add(Artifact(key='provenance-before:' + row.id + ':' + str(row.revision), value={'sections': archived}))
        request_publication(s)
    s.add(row); s.commit()
    s.info.pop('evidence_families', None)
    return row.model_dump()


def evidence_family(s, source):
    """Potential copies never establish independent corroboration by themselves.

    Confirmed family membership is separate. Suggested relationships conservatively
    group evidence until the owner links or explicitly separates the sources.
    """
    if 'evidence_families' not in s.info:
        sources = {x.id: x for x in s.exec(select(Source))}
        parents = {family(x): family(x) for x in sources.values()}
        def root(key):
            while parents[key] != key:
                key = parents[key]
            return key
        for relation in s.exec(select(SourceRelationship)):
            if relation.state not in ('linked', 'suggested') or relation.source_id not in sources or relation.target_id not in sources:
                continue
            a, b = root(family(sources[relation.source_id])), root(family(sources[relation.target_id]))
            if a != b:
                parents[a] = b
        groups = {}
        for member in sources.values():
            groups.setdefault(root(family(member)), []).append(member)
        result = {}
        for members in groups.values():
            # Prefer the existing vault family's key to preserve question identities.
            preferred = sorted({family(x) for x in members if x.provider == 'silverbullet'}) or sorted({family(x) for x in members})
            for member in members:
                result[member.id] = preferred[0]
        s.info['evidence_families'] = result
    return s.info['evidence_families'].get(source.id, family(source))
