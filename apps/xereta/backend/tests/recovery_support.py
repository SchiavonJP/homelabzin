"""Process-level fault injection for operator tests; never imported by the app.

All files/remote responses are synthetic. Only the optional canary uses a real,
separately named Hindsight bank. No crash controls are exposed by the product.
"""
import json
import multiprocessing as mp
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel, select

from app.config import Settings
from app.db import initialize, make_engine
from app.models import Run
from app.services import enqueue
from app.vault import digest

FIXTURE = 'space/Recovery.md'
BODY = '# Synthetic recovery fixture\n\nRecovery snapshots stay local for 14 days.\n'
QUOTE = 'Recovery snapshots stay local for 14 days.'


class Backend:
    """Remote state lives outside the killed worker, with atomic commits."""
    def __init__(self, root):
        self.path = Path(root) / 'remote.sqlite3'

    def connect(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def initialize(self):
        with self.connect() as c:
            c.executescript('''
                CREATE TABLE files (path TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE docs (id TEXT PRIMARY KEY, version TEXT, content TEXT, metadata TEXT);
                CREATE TABLE ops (id TEXT PRIMARY KEY, kind TEXT, status TEXT);
                CREATE TABLE calls (method TEXT, path TEXT, target TEXT);
            ''')
            c.execute('INSERT INTO files VALUES (?,?)', (FIXTURE, BODY))

    def audit(self, method, path, target=''):
        with self.connect() as c:
            c.execute('INSERT INTO calls VALUES (?,?,?)', (method, path, target))

    def rows(self, table):
        if table not in {'files', 'docs', 'ops', 'calls'}:
            raise ValueError('invalid_audit_table')
        with self.connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM ' + table)]

    def body(self, path):
        with self.connect() as c:
            r = c.execute('SELECT body FROM files WHERE path=?', (path,)).fetchone()
        return r['body'] if r else None

    def edit(self, path, body):
        with self.connect() as c:
            c.execute('UPDATE files SET body=? WHERE path=?', (body, path))

    def vault(self, request, stop):
        from urllib.parse import unquote
        path = unquote(request.url.path)
        self.audit(request.method, path)
        if path == '/.fs':
            stop('capture')
            return httpx.Response(200, json=[{'name': FIXTURE, 'size': len(BODY)}])
        name = path.removeprefix('/.fs/')
        if request.method == 'GET':
            body = self.body(name)
            return (httpx.Response(404) if body is None else
                    httpx.Response(200, text=body, headers={'ETag': '"sha256:' + digest(body) + '"'}))
        if request.method == 'PUT':
            stop('publication-intent', name)
            with self.connect() as c:
                row = c.execute('SELECT body FROM files WHERE path=?', (name,)).fetchone()
                etag = '"sha256:' + digest(row['body']) + '"' if row else None
                if ((request.headers.get('if-none-match') == '*' and row) or
                        (request.headers.get('if-match') and request.headers['if-match'] != etag)):
                    return httpx.Response(412)
                c.execute('INSERT INTO files VALUES (?,?) ON CONFLICT(path) DO UPDATE SET body=excluded.body',
                          (name, request.content.decode()))
            stop('publication-accepted', name)
            return httpx.Response(200)
        raise AssertionError('unexpected_vault_request')

    def memory(self, request, stop):
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'healthy'})
        path = request.url.path.split('/banks/', 1)[1].split('/', 1)
        route = '/' + path[1] if len(path) == 2 else ''
        payload = json.loads(request.content) if request.content else {}
        self.audit(request.method, route, payload.get('operation_id', ''))
        if request.method in ('PUT', 'PATCH') and route in ('', '/config'):
            return httpx.Response(200, json={})
        if route.startswith('/operations/'):
            oid = route.rsplit('/', 1)[1]
            with self.connect() as c:
                row = c.execute('SELECT * FROM ops WHERE id=?', (oid,)).fetchone()
            if not row:
                stop('retain-intent', oid)
            return httpx.Response(200, json={'status': row['status']}) if row else httpx.Response(404)
        if request.method == 'POST' and route == '/memories':
            oid = payload['operation_id'];item = payload['items'][0]
            with self.connect() as c:
                c.execute('INSERT INTO ops VALUES (?,?,?) ON CONFLICT DO NOTHING', (oid, 'retain', 'completed'))
                c.execute('INSERT INTO docs VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,content=excluded.content,metadata=excluded.metadata',
                          (item['document_id'], item['metadata']['version'], item['content'], json.dumps(item['metadata'])))
            stop('retain-accepted', oid)
            return httpx.Response(200, json={'success': True, 'operation_id': oid})
        if request.method == 'POST' and route == '/consolidate':
            stop('consolidate-intent')
            oid = str(uuid4())
            with self.connect() as c:
                c.execute('INSERT INTO ops VALUES (?,?,?)', (oid, 'consolidation', 'completed'))
            stop('consolidate-accepted', oid)
            return httpx.Response(200, json={'operation_id': oid})
        if route.startswith('/documents/'):
            with self.connect() as c:
                row = c.execute('SELECT * FROM docs WHERE id=?', (route.rsplit('/', 1)[1],)).fetchone()
            return httpx.Response(200, json={'original_text': row['content'], 'document_metadata': json.loads(row['metadata'])})
        if route == '/memories/list':
            return httpx.Response(200, json={'items': [{'id': r['id'], 'fact_type': 'world'} for r in self.rows('docs')]})
        if route.startswith('/memories/'):
            return httpx.Response(200, json={'document_id': route.rsplit('/', 1)[1]})
        raise AssertionError('unexpected_memory_request')


def guarded_database(url):
    parsed = make_url(url)
    if parsed.get_backend_name() == 'sqlite':
        return
    if parsed.get_backend_name() != 'postgresql' or not re.fullmatch('xereta_recovery_[a-f0-9]{12}', parsed.database or ''):
        raise ValueError('disposable_recovery_database_required')


def setup_case(root, database_url=None, real_bank=None, runtime=None):
    root = Path(root);root.mkdir(parents=True, exist_ok=True, mode=0o700)
    url = database_url or 'sqlite:///' + str(root / 'state.sqlite3')
    guarded_database(url)
    parsed = make_url(url)
    if parsed.get_backend_name() == 'sqlite' and Path(parsed.database or '').resolve() != (root / 'state.sqlite3').resolve():
        raise ValueError('sqlite_state_must_be_inside_recovery_directory')
    settings = Settings(database_url=url, state_path=root,
        secret_key=secrets.token_urlsafe(48), owner_password=secrets.token_urlsafe(32),
        agent_read_token=secrets.token_urlsafe(48), publish_enabled=True, acceptance_passed=False,
        pilot_paths=[FIXTURE], hindsight_bank=real_bank or 'knowledge-vault-recovery-' + uuid4().hex,
        hindsight_url=runtime.hindsight_url if runtime else 'http://127.0.0.1:8888',
        hindsight_token=runtime.hindsight_token if runtime else '', silverbullet_token='', litellm_key='')
    engine = make_engine(url)
    if engine.dialect.name == 'postgresql':
        # The name guard and dedicated role are mandatory before destructive reset.
        with engine.begin() as c:
            c.execute(text('DROP SCHEMA public CASCADE'))
            c.execute(text('CREATE SCHEMA public'))
    initialize(engine, settings)
    Backend(root).initialize()
    with Session(engine) as s:
        job = enqueue(s, 'recovery:' + uuid4().hex)
        run_id = job.id
    engine.dispose()
    return settings, run_id


def child_tick(settings_data, armed, pipe, real_memory=False):
    """Spawn target: patch adapters in this process only, then use the real worker."""
    from app import services, worker
    from app.memory import Memory, validate_review
    from app.vault import Vault
    settings = Settings(**settings_data)
    guarded_database(settings.database_url)
    if not settings.hindsight_bank.startswith('knowledge-vault-recovery-'):
        raise ValueError('isolated_recovery_bank_required')
    backend = Backend(settings.state_path)

    def stop(point, value=''):
        if point == armed:
            pipe.send({'point': point, 'value': value})
            pipe.recv()  # The parent either releases this barrier or kills us.

    class CanaryMemory(Memory):
        def retain(self, *args, **kwargs):
            backend.audit('POST_REAL', '/memories', args[3])
            super().retain(*args, **kwargs)
            stop('retain-accepted', args[3])

    services.Vault = lambda cfg: Vault(cfg, httpx.MockTransport(lambda req: backend.vault(req, stop)))
    services.Memory = (CanaryMemory if real_memory else
                       lambda cfg: Memory(cfg, httpx.MockTransport(lambda req: backend.memory(req, stop))))

    def synthetic_draft(cfg, sources, versions, trusted):
        data = {'items': [
            {'issue': 'synthetic-recovery-question', 'kind': 'question', 'text': 'Synthetic recovery question?',
             'reason': 'Recovery fixture only.', 'evidence': [{'source_id': sources[0].id, 'quote': QUOTE}]},
            {'issue': 'synthetic-recovery-fact', 'kind': 'finding', 'text': 'Synthetic retention statement.',
             'reason': 'Recovery fixture only.', 'evidence': [{'source_id': sources[0].id, 'quote': QUOTE}]}]}
        return validate_review(data, sources, versions, trusted)

    services.draft = synthetic_draft
    engine = make_engine(settings.database_url)
    try:
        worker.tick(engine, settings)
    finally:
        engine.dispose()
        pipe.close()


class WorkerProcess:
    def __init__(self, settings, armed='', real_memory=False):
        ctx = mp.get_context('spawn')
        self.pipe, child = ctx.Pipe()
        self.process = ctx.Process(target=child_tick,
            args=(settings.model_dump(), armed, child, real_memory))
        self.process.start();child.close()

    def barrier(self, seconds=30):
        if not self.pipe.poll(seconds):
            raise AssertionError('recovery_barrier_not_reached')
        return self.pipe.recv()

    def kill(self):
        if self.process.is_alive():
            self.process.kill()
        self.process.join(10)
        if self.process.is_alive():
            raise AssertionError('recovery_worker_not_stopped')
        self.pipe.close()

    def finish(self, seconds=30):
        self.process.join(seconds)
        if self.process.is_alive():
            self.kill()
            raise AssertionError('recovery_worker_timeout')
        self.pipe.close()
        if self.process.exitcode != 0:
            raise AssertionError('recovery_worker_process_failed')


def run_state(settings, run_id):
    engine = make_engine(settings.database_url)
    try:
        with Session(engine) as s:
            r = s.get(Run, run_id)
            return {'id': r.id, 'state': r.state, 'stage': r.stage, 'started_at': r.started_at,
                    'error': r.error, 'result': r.result}
    finally:
        engine.dispose()
