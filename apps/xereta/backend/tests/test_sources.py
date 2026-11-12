"""Owner approval, stable batches, and retention boundaries."""
import pytest
from sqlmodel import Session, select

from test_xereta import client, settings, owner, seed
from app.models import Artifact, Event, Run, Schedule, Source, Version
from app.services import capture_sources, current_versions, answer_question
from app.source_selection import KEY, catalogue, choose, selection
from app.vault import Capture, DomainError, digest


class VaultStub:
    def __init__(self):
        self.files = {'space/New.md': '# New\nA personal note.', 'space/Other.md': '# Other\nAnother note.'}
        self.reads = []
    def inventory(self):
        return [{'path': path, 'size': len(body.encode())} for path, body in self.files.items()]
    def capture(self, path):
        self.reads.append(path)
        body = self.files[path]
        if not body.strip():
            raise DomainError('empty_capture', 422)
        return Capture(path, body, digest(body), '"sha256:' + digest(body) + '"')
    def permalink(self, path):
        return 'https://silverbullet.joaopaulo.me/' + path.removesuffix('.md')
    def close(self): pass


def test_catalogue_is_metadata_only_and_owner_only(client, settings, monkeypatch):
    vault = VaultStub()
    monkeypatch.setattr('app.main.Vault', lambda _: vault)
    reader = {'Authorization': 'Bearer ' + settings.agent_read_token.get_secret_value()}
    path = '/api/v1/xereta/source-catalog'
    assert client.get(path).status_code == 401
    assert client.get(path, headers=reader).status_code == 403
    assert client.put('/api/v1/xereta/source-selection', headers=reader,
                      json={'paths': ['space/New.md'], 'expected_revision': 0}).status_code == 403
    response = client.get(path, headers=owner(client, settings))
    assert response.status_code == 200 and not vault.reads
    assert len(response.json()['selection']['paths']) == 3
    assert 'body' not in response.json()['notes'][0]
    with Session(client.app.state.engine) as s:
        assert not s.get(Artifact, KEY)
        assert not s.exec(select(Source)).all() and not s.exec(select(Run)).all()


def test_selection_saves_without_ingestion_and_preserves_prior_review(client, settings, monkeypatch):
    vault = VaultStub()
    monkeypatch.setattr('app.main.Vault', lambda _: vault)
    with Session(client.app.state.engine) as s:
        src, version, q = seed(s)
        answer_question(s, q.id, 'Keep 14 days.', 'confirmed', 0)
        before = s.get(Schedule, 1).model_dump()
        sid, vid, qid = src.id, version.id, q.id
    headers = owner(client, settings)
    response = client.put('/api/v1/xereta/source-selection', headers=headers,
                          json={'paths': ['space/New.md'], 'expected_revision': 0})
    assert response.status_code == 200 and response.json()['revision'] == 1
    assert response.json()['paths'] == ['space/New.md']
    with Session(client.app.state.engine) as s:
        assert s.get(Source, sid).approved and s.get(Version, vid).body == 'Guardar 14 dias.'
        from app.models import Question
        assert s.get(Question, qid).state == 'resolved'
        assert s.get(Schedule, 1).model_dump() == before
        assert not s.exec(select(Run)).all()
        assert not s.exec(select(Source).where(Source.path == 'space/New.md')).first()
        assert s.exec(select(Event).where(Event.kind == 'source_selection_changed')).one()
        # Only selected originals enter the next intake; feedback always follows.
        captured, versions = capture_sources(s, settings, vault)
        assert [x.path for x in captured] == ['space/New.md']
        ids = {x.id for x in captured}
        all_sources, _ = current_versions(s)
        active, _ = current_versions(s, original_paths=['space/New.md'])
        assert sid in {x.id for x in all_sources} and sid not in {x.id for x in active}
        assert any(x.path.startswith('feedback:') for x in active)
        count = len(s.exec(select(Version)).all())
        capture_sources(s, settings, vault)
        assert len(s.exec(select(Version)).all()) == count
        assert set(versions) == ids
        assert selection(s, settings)['paths'] == ['space/New.md']


@pytest.mark.parametrize('paths', [[], ['space/New.md'] * 2, ['space/New.md'] * 4,
    ['space/../secret.md'], ['space/_AgentKnowledge/Inbox.md'], ['space/Missing.md']])
def test_invalid_selection_does_not_change_batch(client, settings, paths):
    with Session(client.app.state.engine) as s:
        with pytest.raises(DomainError): choose(s, settings, VaultStub(), paths, 0)
        assert not s.get(Artifact, KEY)
        assert selection(s, settings)['revision'] == 0


@pytest.mark.parametrize('body,reason', [('', 'empty_capture'), ('x' * 24001, 'source_selection_note_oversized'),
    ('---\ngenerated: true\n---\nSystem content', 'generated_source_excluded')])
def test_unusable_notes_cannot_be_approved(client, settings, body, reason):
    vault = VaultStub(); vault.files['space/New.md'] = body
    with Session(client.app.state.engine) as s:
        with pytest.raises(DomainError, match=reason): choose(s, settings, vault, ['space/New.md'], 0)
        assert not s.get(Artifact, KEY)


def test_stale_revision_and_active_run_block_changes(client, settings):
    vault = VaultStub()
    with Session(client.app.state.engine) as s:
        choose(s, settings, vault, ['space/New.md'], 0)
        with pytest.raises(DomainError, match='source_selection_revision_conflict'):
            choose(s, settings, vault, ['space/Other.md'], 0)
        for state in ('queued', 'running'):
            run = Run(key='test-' + state, state=state); s.add(run); s.commit()
            with pytest.raises(DomainError, match='source_selection_run_active'):
                choose(s, settings, vault, ['space/Other.md'], 1)
            s.delete(run); s.commit()
        assert selection(s, settings)['paths'] == ['space/New.md']
        choose(s, settings, vault, ['space/Other.md'], 1)
        assert 'space/New.md' in selection(s, settings)['approved_paths']
        del vault.files['space/Other.md']
        missing = next(n for n in catalogue(s, settings, vault)['notes'] if n['active'])
        assert missing['available'] is False


def test_postgresql_selection_and_enqueue_share_lock(tmp_path):
    """The queued job boundary and batch change cannot cross each other."""
    import os
    import threading
    import time
    from sqlalchemy import text
    from app.db import initialize, make_engine
    from app.services import enqueue
    from recovery_support import guarded_database
    url = os.environ.get('XERETA_RECOVERY_DATABASE_URL')
    if not url:
        pytest.skip('operator supplies a disposable PostgreSQL database')
    guarded_database(url)
    from test_xereta import Settings, secrets
    cfg = Settings(database_url=url, secret_key=secrets.token_urlsafe(48),
        owner_password=secrets.token_urlsafe(32), agent_read_token=secrets.token_urlsafe(48), state_path=tmp_path)
    engine = make_engine(url)
    initialize(engine, cfg)
    with Session(engine) as s:
        for run in s.exec(select(Run)).all(): s.delete(run)
        previous = s.get(Artifact, KEY)
        if previous: s.delete(previous)
        s.commit()
    ready, done = threading.Event(), threading.Event()
    result = []
    def change():
        try:
            with Session(engine) as contender:
                ready.set()
                choose(contender, cfg, VaultStub(), ['space/New.md'], 0)
        except DomainError as e: result.append(e.code)
        except Exception as e: result.append(type(e).__name__)
        finally: done.set()
    try:
        with Session(engine) as holder:
            holder.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 1481855590})
            thread = threading.Thread(target=change, daemon=True); thread.start()
            assert ready.wait(5)
            assert not done.wait(.2)
            enqueue(holder, 'source-lock-test')
            assert done.wait(10)
            thread.join(5)
        assert result == ['source_selection_run_active']
        with Session(engine) as s:
            assert not s.get(Artifact, KEY)
    finally:
        engine.dispose()
