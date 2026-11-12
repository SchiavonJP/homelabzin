"""Private before/after verification for the Sources rollout. Run inside app."""
import argparse
import contextlib
import json
from pathlib import Path

import httpx
from sqlmodel import Session, select
from app.config import Settings
from app.db import make_engine
from app.models import Artifact, Feedback, Finding, Publication, Question, ReviewPage, Run, Schedule, Source, User, Version
from app.services import save_private
from app.vault import Vault, digest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('phase', choices=['baseline', 'verify'])
args = parser.parse_args()
cfg = Settings()
engine = make_engine(cfg.database_url)
path = cfg.state_path / 'releases' / '0.3.0' / 'baseline.json'
with Session(engine) as s, contextlib.closing(Vault(cfg)) as vault:
    if s.exec(select(Run).where(Run.state.in_(['queued', 'running']))).first():
        raise SystemExit('active_run_exists')
    tables = {}
    for model in (Artifact, Feedback, Finding, Publication, Question, ReviewPage, Run, Schedule, Source, User, Version):
        rows = sorted(json.dumps(x.model_dump(), sort_keys=True) for x in s.exec(select(model)))
        tables[model.__name__] = {'count': len(rows), 'digest': digest(json.dumps(rows))}
    files = {}
    for src in s.exec(select(Source)):
        if src.path.startswith('space/'): files[src.path] = vault.capture(src.path).hash
    for page in s.exec(select(ReviewPage)):
        files[page.path] = vault.capture(page.path).hash
    state = {'tables': tables, 'files': files, 'schedule': s.get(Schedule, 1).model_dump()}
    if args.phase == 'baseline':
        if path.exists(): raise SystemExit('baseline_already_exists')
        save_private(path, json.dumps(state))
        print(json.dumps({'baseline_saved': True, 'files': len(files), 'schedule': state['schedule']}))
    else:
        before = json.loads(path.read_text())
        if state != before: raise SystemExit('release_state_changed')
        with httpx.Client(base_url='http://127.0.0.1:3101', timeout=20, trust_env=False) as client:
            login = client.post('/api/v1/login/access-token', json={'email': cfg.owner_email, 'password': cfg.owner_password.get_secret_value()})
            if login.status_code != 200: raise SystemExit('owner_login_failed')
            headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
            response = client.get('/api/v1/xereta/source-catalog', headers=headers)
            if response.status_code != 200: raise SystemExit('source_catalog_failed')
            data = response.json()
            if not 1 <= len(data['selection']['paths']) <= 3: raise SystemExit('invalid_batch_size')
            reader = {'Authorization': 'Bearer ' + cfg.agent_read_token.get_secret_value()}
            if client.get('/api/v1/xereta/source-catalog', headers=reader).status_code != 403:
                raise SystemExit('reader_catalog_access')
            if client.get('/health/ready').status_code != 200: raise SystemExit('worker_not_ready')
        report = {'release': '0.3.0', 'state_preserved': True, 'files_unchanged': len(files),
                  'schedule_unchanged': True, 'owner_login_passed': True, 'reader_denied': True,
                  'catalogue_notes': len(data['notes']), 'selected_notes': len(data['selection']['paths']),
                  'prior_runs': tables['Run']['count'], 'worker_ready': True}
        save_private(path.with_name('verified.json'), json.dumps(report))
        print(json.dumps(report))
