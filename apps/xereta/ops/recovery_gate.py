#!/usr/bin/env python3
"""Proxmox-root recovery qualification; private state, no public fault controls.

Stages: isolated -> canary -> live -> verify -> cleanup. Requires the checkout
at /root/xereta-recovery-src in CT107; uses a dedicated role/database in CT104.
No external dependencies are needed on Proxmox. App imports run inside Docker.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

SOURCE = '/root/xereta-recovery-src'
ROOT = Path('/root/xereta-recovery')
PCT = '/usr/sbin/pct'


class GateError(Exception):
    pass


def write_private(path, data):
    path = Path(path);path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name('.' + path.name + '-' + secrets.token_hex(8))
    with tmp.open('x', encoding='utf-8') as f:
        tmp.chmod(0o600);f.write(data);f.flush();os.fsync(f.fileno())
    tmp.replace(path)


def command(argv, body=None, timeout=90, log=None):
    try:
        r = subprocess.run(argv, input=body, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise GateError('command_timeout') from None
    if log:
        write_private(log, (r.stdout + r.stderr).decode(errors='replace'))
    if r.returncode:
        raise GateError('command_failed')
    return r.stdout


def guest(ct, argv, **kwargs):
    return command([PCT, 'exec', str(ct), '--', *argv], **kwargs)


def guest_python(code):
    return guest(107, ['python3', '-'], body=code.encode())


def stage_digest():
    code = """
from pathlib import Path
import hashlib,json
root=Path('/root/xereta-recovery-src');h=hashlib.sha256()
files=list((root/'backend').rglob('*.py'))+list((root/'ops').rglob('*.py'))
files += [root/'compose.yml', root/'Dockerfile', root/'backend/requirements.lock']
for p in sorted(files):
 if '__pycache__' not in p.parts and not p.name.startswith('._'):
  h.update(str(p.relative_to(root)).encode());h.update(p.read_bytes())
print(json.dumps(h.hexdigest()))
"""
    return json.loads(guest_python(code))


def db_admin(body):
    return guest(104, ['docker', 'exec', '-i', 'sb_postgres', 'sh', '-c',
        'psql -At -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres'], body=body.encode())


def inner(phase, identifier):
    return json.loads(guest(107, ['docker', 'exec', '-i', 'sb_xereta', 'python', '-', '_inside', phase, identifier],
        body=Path(__file__).read_bytes(), timeout=90))


def inside(phase, identifier):
    """Runs in the application container. Never prints settings or note bodies."""
    from sqlmodel import Session, select
    from app.config import Settings
    from app.db import make_engine
    from app.memory import Memory
    from app.models import Artifact, Feedback, Finding, Question, ReviewPage, Run, Schedule, Source, Version
    from app.services import current_versions, enqueue, save_private
    from app.vault import Vault, digest, INBOX
    cfg = Settings();engine = make_engine(cfg.database_url);vault = Vault(cfg)
    from sqlalchemy.engine import make_url
    if make_url(cfg.database_url).database != 'knowledge_curator' or cfg.hindsight_bank != 'knowledge-vault-pilot':
        raise GateError('unexpected_live_target')
    directory = cfg.state_path / 'gates' / 'recovery' / identifier

    def snapshot(s):
        sources, versions = current_versions(s)
        pages = list(s.exec(select(ReviewPage)))
        if not all(v.state == 'complete' for v in versions.values()):
            raise GateError('unfinished_versions')
        if len([x for x in sources if x.path.startswith('space/')]) != 3:
            raise GateError('pilot_scope_changed')
        fingerprint = digest(json.dumps([(x.id, versions[x.id].hash) for x in sources]))
        if not s.get(Artifact, 'review:' + fingerprint):
            raise GateError('unchanged_review_cache_required')
        files = {p.path: vault.capture(p.path).hash for p in pages}
        if not all(files[p.path] == digest(p.body) and p.state == 'published' and not p.error for p in pages):
            raise GateError('unpublished_or_edited_review')
        files.update({x.path: vault.capture(x.path).hash for x in sources if x.path.startswith('space/')})
        if not all(files[x.path] == x.version for x in sources if x.path.startswith('space/')):
            raise GateError('original_source_changed')
        files[INBOX] = vault.capture(INBOX).hash
        sync = s.get(Artifact, 'sync-check:current')
        if not sync or sync.value.get('state') != 'passed':
            raise GateError('owner_sync_gate_required')
        files[sync.value['path']] = vault.capture(sync.value['path']).hash
        return {
            'sources': sorted((x.id, x.path, x.version, x.state) for x in sources),
            'versions': sorted((v.id, v.source_id, v.hash, v.operation_id, v.state) for v in s.exec(select(Version))),
            'questions': sorted((q.id, q.revision, q.state, q.disposition, digest(q.answer), digest(json.dumps(q.evidence, sort_keys=True))) for q in s.exec(select(Question))),
            'findings': sorted((f.id, f.revision, f.state, digest(f.text), digest(json.dumps(f.evidence, sort_keys=True))) for f in s.exec(select(Finding))),
            'feedback': sorted((f.id, f.question_id, f.disposition, f.state, digest(f.answer)) for f in s.exec(select(Feedback))),
            'files': files,
        }

    try:
        if phase == 'cleanup-bank':
            bank = 'knowledge-vault-recovery-' + identifier
            memory = Memory(cfg.model_copy(update={'hindsight_bank': bank}))
            try:
                result = memory.call('DELETE', missing=True)
                print(json.dumps({'bank_deleted': result is None or bool(result.get('success'))}));return
            finally:
                memory.close()
        with Session(engine) as s:
            if cfg.acceptance_passed or s.get(Schedule, 1).enabled:
                raise GateError('schedule_must_be_disabled')
            if phase == 'baseline':
                if s.exec(select(Run).where(Run.state.in_(['queued', 'running']))).first():
                    raise GateError('active_run_exists')
                if s.exec(select(Feedback).where(Feedback.state == 'pending')).first():
                    raise GateError('pending_feedback_exists')
                data = {'snapshot': snapshot(s), 'recorded_at': datetime.now(timezone.utc).isoformat(),
                        'run_count': len(list(s.exec(select(Run))))}
                save_private(directory / 'baseline.json', json.dumps(data))
                print(json.dumps({'baseline_saved': True, 'files': len(data['snapshot']['files'])}));return
            before = json.loads((directory / 'baseline.json').read_text())
            if phase == 'stop':
                rid = json.loads((directory / 'run.json').read_text())['run_id']
                run = s.get(Run, rid)
                if not run or run.key != 'recovery-live:' + identifier:
                    raise GateError('unexpected_stop_target')
                if run.state in ('queued', 'running'):
                    run.stop_requested = True;s.add(run);s.commit()
                print(json.dumps({'stop_requested_for': rid}));return
            if phase == 'queue':
                if snapshot(s) != {k: [tuple(x) for x in v] if isinstance(v,list) else v for k,v in before['snapshot'].items()}:
                    raise GateError('baseline_changed_before_queue')
                job = enqueue(s, 'recovery-live:' + identifier)
                if job.state != 'queued':
                    raise GateError('worker_must_be_stopped_before_queue')
                save_private(directory / 'run.json', json.dumps({'run_id': job.id}))
                print(json.dumps({'run_id': job.id, 'state': job.state}));return
            if phase == 'verify':
                rid = json.loads((directory / 'run.json').read_text())['run_id'];run = s.get(Run, rid)
                if run.state in ('queued', 'running'):
                    print(json.dumps({'status': 'pending', 'run_id': rid, 'state': run.state}));return
                after = snapshot(s)
                expected = {k: [tuple(x) for x in v] if isinstance(v,list) else v for k,v in before['snapshot'].items()}
                checks = {k + '_preserved': after[k] == expected[k] for k in expected}
                checks.update({'same_run_completed': run.state == 'completed' and not run.error,
                    'one_run_added': len(list(s.exec(select(Run)))) == before['run_count'] + 1,
                    'publication_complete': run.result.get('publication') == 'published',
                    'schedule_disabled': not cfg.acceptance_passed and not s.get(Schedule,1).enabled})
                report = {'gate': 'recovery-live-queued-restart', 'passed': all(checks.values()),
                          'checks': checks, 'run_id': rid, 'started_at': run.started_at,
                          'finished_at': run.finished_at, 'error': run.error}
                save_private(directory / 'live-result.json', json.dumps(report))
                print(json.dumps(report));return
            raise GateError('invalid_inside_phase')
    finally:
        vault.close();engine.dispose()


def canary(identifier):
    # This entry point runs in an isolated container with a dedicated DB role.
    base = Path(__file__).resolve().parents[1]
    tests = base / 'backend' / 'tests'
    if not tests.is_dir():
        tests = base / 'tests'
    sys.path.insert(0, str(tests))
    from sqlmodel import Session, select
    from app.config import Settings
    from app.db import make_engine
    from app.memory import Memory
    from app.models import Source, Version
    from app.services import save_private
    from recovery_support import Backend, WorkerProcess, guarded_database, run_state, setup_case
    url = os.environ['XERETA_RECOVERY_DATABASE_URL'];guarded_database(url)
    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    if parsed.get_backend_name() != 'postgresql' or parsed.database != 'xereta_recovery_' + identifier:
        raise GateError('canary_database_identity_mismatch')
    state = Path('/data/canary');state.mkdir(exist_ok=True, mode=0o700)
    runtime = Settings()
    bank = 'knowledge-vault-recovery-' + identifier
    cfg, rid = setup_case(state, url, bank, runtime)
    first = WorkerProcess(cfg, 'retain-accepted', real_memory=True)
    try:
        barrier = first.barrier(180)
        before = run_state(cfg, rid)
    finally:
        first.kill()
    replacement = WorkerProcess(cfg, real_memory=True)
    try:
        replacement.finish(1200)
    finally:
        replacement.kill()
    result = run_state(cfg, rid);memory = Memory(cfg);engine = make_engine(url)
    try:
        with Session(engine) as s:
            source = s.exec(select(Source)).one();version = s.exec(select(Version)).one()
            memory.verify(source, version)
            docs = memory.call('GET', '/documents?limit=100')
            operations = memory.call('GET', '/operations?limit=100')['operations']
            retains = [x for x in operations if x.get('task_type') == 'retain']
            batches = [x for x in operations if x.get('task_type') == 'batch_retain']
            checks = {'same_run_completed': result['id'] == rid and result['state'] == 'completed',
                'publication_complete': result['result'].get('publication') == 'published',
                'same_start_preserved': result['started_at'] == before['started_at'],
                'retention_operation_reused': version.operation_id == barrier['value'],
                'one_retention_request': len([x for x in Backend(state).rows('calls') if x['method']=='POST_REAL']) == 1,
                'one_remote_document': docs['total'] == 1 and docs['items'][0]['id'] == source.id,
                # /memories creates one batch with the caller's ID and one
                # internal item operation. Neither should be duplicated.
                'one_remote_retention_batch': len(batches) == 1 and batches[0]['id'] == version.operation_id,
                'one_remote_item_retention': len(retains) == 1,
                'verified_document_complete': source.state == version.state == 'complete',
                'isolated_bank': bank != runtime.hindsight_bank and bank.startswith('knowledge-vault-recovery-')}
            report = {'gate': 'recovery-real-hindsight-canary', 'passed': all(checks.values()),
                'checks': checks, 'bank': bank, 'run_id': rid, 'operation_id': version.operation_id,
                'started_at': result['started_at'], 'error': result['error']}
            save_private(Path('/data/canary-result.json'), json.dumps(report))
            print(json.dumps(report))
            if not report['passed']:
                raise GateError('canary_checks_failed')
    finally:
        engine.dispose();memory.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['isolated', 'canary', 'live', 'verify', 'cleanup'])
    parser.add_argument('--id', required=True)
    parser.add_argument('--image', choices=['xereta:0.2.2', 'xereta:0.2.3'], default='xereta:0.2.3')
    args = parser.parse_args();identifier = args.id
    if not re.fullmatch('[a-f0-9]{12}', identifier):
        raise GateError('invalid_recovery_id')
    if os.geteuid() != 0 or not Path(PCT).exists():
        raise GateError('run_on_proxmox_as_root')
    directory = ROOT / identifier;manifest_path = directory / 'private.json'
    host = '/root/xereta/recovery/' + identifier
    if args.phase == 'isolated' and not manifest_path.exists():
        password = secrets.token_urlsafe(36)
        manifest = {'id': identifier, 'database': 'xereta_recovery_' + identifier,
                    'role': 'xereta_recovery_' + identifier, 'password': password}
        write_private(manifest_path, json.dumps(manifest))
    manifest = json.loads(manifest_path.read_text())
    role = manifest['role'];database = manifest['database']
    if role != 'xereta_recovery_' + identifier or database != role:
        raise GateError('resource_identity_mismatch')
    if not re.fullmatch('[A-Za-z0-9_-]+', manifest['password']):
        raise GateError('invalid_generated_password')

    def save(phase, report):
        report.update({'identifier': identifier, 'recorded_at': datetime.now(timezone.utc).isoformat()})
        write_private(directory / (phase + '.json'), json.dumps(report))
        print(json.dumps(report))

    def require(phase):
        report = json.loads((directory / (phase + '.json')).read_text())
        if not report['passed'] or report.get('source_digest') != stage_digest():
            raise GateError('prior_gate_missing_or_source_changed')

    if args.phase == 'isolated':
        definitions = '\\set role ' + role + '\n\\set database ' + database + '\n\\set password ' + manifest['password'] + '\n'
        sql = definitions + r"""
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 8', :'role', :'password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname=:'role')\gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'database', :'role')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname=:'database')\gexec
"""
        db_admin(sql)
        env = 'XERETA_RECOVERY_DATABASE_URL=postgresql+psycopg://' + role + ':' + manifest['password'] + '@192.168.0.210:5432/' + database + '\n'
        code = "from pathlib import Path\nimport os\nos.umask(0o077)\np=Path(" + repr(host) + ");p.mkdir(parents=True,exist_ok=True,mode=0o700)\n(p/'database.env').write_text(" + repr(env) + ")\ns=p/'state';s.mkdir(exist_ok=True,mode=0o700);os.chown(s,10001,10001)\n"
        guest_python(code)
        name = 'xereta_recovery_matrix_' + identifier
        try:
            guest(107, ['docker','run','--rm','--name',name,'--network','host',
                '--env-file',host+'/database.env','--volume',SOURCE+':/recovery:ro',
                '--volume',host+'/state:/data','--workdir','/recovery/backend','--entrypoint','python',args.image,
                '-m','pytest','-q','-p','no:cacheprovider','--junitxml=/data/matrix.xml','tests/test_recovery.py'],
                timeout=600, log=directory/'matrix.log')
        finally:
            subprocess.run([PCT,'exec','107','--','docker','rm','-f',name],
                           capture_output=True, timeout=30)
        xml = guest(107, ['cat',host+'/state/matrix.xml'])
        suites = ET.fromstring(xml).iter('testsuite')
        totals = {k: 0 for k in ('tests','failures','errors','skipped')}
        for suite in suites:
            for k in totals:totals[k] += int(suite.get(k, '0'))
        passed = totals['tests'] >= 10 and not any(totals[k] for k in ('failures','errors','skipped'))
        save('isolated', {'gate':'recovery-isolated-postgresql','passed':passed,'tests':totals,'source_digest':stage_digest()})
        if not passed:raise GateError('isolated_matrix_failed')
    elif args.phase == 'canary':
        require('isolated')
        name = 'xereta_recovery_canary_' + identifier
        try:
            raw = guest(107, ['docker','run','--rm','--name',name,'--network','host',
                '--env-file','/root/xereta/.env','--env-file',host+'/database.env',
                '--volume',SOURCE+':/recovery:ro','--volume',host+'/state:/data',
                '--workdir','/recovery/backend','--entrypoint','python',args.image,
                '/recovery/ops/recovery_gate.py','_canary',identifier], timeout=1400, log=directory/'canary.log')
        finally:
            subprocess.run([PCT,'exec','107','--','docker','rm','-f',name],
                           capture_output=True, timeout=30)
        report = json.loads(raw);report['source_digest'] = stage_digest();save('canary', report)
    elif args.phase == 'live':
        require('isolated');require('canary')
        if args.image != 'xereta:0.2.3' or manifest.get('backup_database'):
            raise GateError('live_requires_new_release_and_unused_live_gate')
        guest(107,['docker','image','inspect','xereta:0.2.3'])
        for name in ('sb_xereta','sb_xereta_worker'):
            if guest(107,['docker','inspect','--format','{{.State.Running}}',name]).strip() != b'true':
                raise GateError('live_services_must_be_running')
        baseline = inner('baseline',identifier)
        backup_name = 'xereta_recovery_restore_' + identifier
        manifest['backup_database'] = backup_name
        write_private(manifest_path,json.dumps(manifest))
        definitions = '\\set database ' + backup_name + '\n'
        db_admin(definitions + "SELECT format('CREATE DATABASE %I', :'database')\\gexec\n")
        dump = guest(104, ['docker','exec','sb_postgres','sh','-c','pg_dump -U "$POSTGRES_USER" -Fc knowledge_curator'],timeout=120)
        dump_path = directory/'database.dump'
        with dump_path.open('wb') as f:f.write(dump)
        dump_path.chmod(0o600)
        guest(104,['docker','exec','-i','sb_postgres','sh','-c','pg_restore -U "$POSTGRES_USER" --no-owner --no-privileges --exit-on-error -d "$1"','--',backup_name],body=dump,timeout=120)
        # Compare table rows without exposing their contents; require identical digests.
        compare = """SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"""
        def psql(db, body):
            return guest(104,['docker','exec','-i','sb_postgres','sh','-c','psql -At -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"','--',db],body=body.encode())
        tables=psql('knowledge_curator',compare).decode().splitlines();same=True
        for table in tables:
            if not re.fullmatch('[a-z_][a-z0-9_]*',table):raise GateError('unexpected_table_name')
            query='SELECT count(*),md5(coalesce(string_agg(to_jsonb(t)::text,\'\' ORDER BY to_jsonb(t)::text),\'\')) FROM public."'+table+'" t;'
            # pg_dump is transactionally consistent, but the live heartbeat
            # advances while the restore is checked. Its row count is stable;
            # all application data tables still require exact row digests.
            if table == 'heartbeat':
                query = 'SELECT count(*) FROM public.heartbeat;'
            same=same and psql('knowledge_curator',query)==psql(backup_name,query)
        if not same:raise GateError('backup_restore_mismatch')
        archive=guest(107,['docker','exec','sb_xereta','tar','-C','/data','-czf','-','.'],timeout=120)
        with (directory/'state-before.tgz').open('wb') as f:f.write(archive)
        (directory/'state-before.tgz').chmod(0o600)
        guest(107,['tar','-C','/root/xereta-app','-czf',host+'/checkout-before.tgz','.'],timeout=120)
        guest(107,['chmod','600',host+'/checkout-before.tgz'])
        old_image=guest(107,['docker','inspect','--format','{{.Image}}','sb_xereta']).decode().strip()
        guest(107,['docker','tag',old_image,'xereta:before-recovery-'+identifier])
        manifest['backup_database']=backup_name;manifest['backup_verified']=True;manifest['old_image']=old_image
        write_private(manifest_path,json.dumps(manifest))
        guest_python("import shutil\nfrom pathlib import Path\ns=Path('/root/xereta-recovery-src');d=Path('/root/xereta-app')\nfor name in ('backend','ops'):\n shutil.copytree(s/name,d/name,dirs_exist_ok=True)\nfor name in ('compose.yml','Dockerfile'):\n shutil.copy2(s/name,d/name)\n")
        compose = ['docker','compose','--project-directory','/root/xereta-app','-f','/root/xereta-app/compose.yml','up','-d','--no-build','--pull','never','app','worker']
        try:
            guest(107,compose,timeout=120)
            ready_until = time.monotonic() + 90
            while True:
                try:
                    guest(107,['docker','exec','sb_xereta','python','-c',
                        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3101/health/ready',timeout=5)"])
                    break
                except GateError:
                    if time.monotonic() >= ready_until:
                        raise GateError('new_release_not_ready')
                    time.sleep(3)
        except GateError:
            # Roll back code/image only. Never restore the production DB over
            # possible newer owner edits as an automatic recovery action.
            guest(107,['tar','-xzf',host+'/checkout-before.tgz','-C','/root/xereta-app'])
            guest(107,compose,timeout=120)
            guest(107,['docker','start','sb_xereta_worker'])
            raise GateError('deployment_failed_previous_release_restored') from None
        try:
            guest(107,['docker','stop','--time','10','sb_xereta_worker'],timeout=30)
            queued=inner('queue',identifier)
        finally:
            guest(107,['docker','start','sb_xereta_worker'])
        deadline=time.monotonic()+120
        while True:
            report=inner('verify',identifier)
            if report.get('status')!='pending':break
            if time.monotonic()>=deadline:
                inner('stop',identifier)
                raise GateError('live_recovery_timeout')
            time.sleep(3)
        report.update({'source_digest':stage_digest(),'backup_restore_verified':True,'backup_tables':len(tables),
            'backup_heartbeat_comparison':'row count; live heartbeat timestamps advance',
            'baseline_files':baseline['files'],'restart_mode':'worker stopped, unchanged run queued, worker started'})
        save('live',report)
        if not report['passed']:raise GateError('live_verification_failed')
    elif args.phase == 'verify':
        report=inner('verify',identifier)
        save('verification',report)
        if not report.get('passed'):raise GateError('live_verification_failed')
    elif args.phase == 'cleanup':
        result=inner('cleanup-bank',identifier)
        databases=[database]
        if manifest.get('backup_database'):databases.append(manifest['backup_database'])
        for db in databases:
            if not re.fullmatch('xereta_recovery_(?:restore_)?'+identifier,db):raise GateError('unsafe_cleanup_target')
            definitions='\\set database '+db+'\n'
            db_admin(definitions+"SELECT format('DROP DATABASE IF EXISTS %I', :'database')\\gexec\n")
        db_admin('\\set role '+role+'\n'+"SELECT format('DROP ROLE IF EXISTS %I', :'role')\\gexec\n")
        # Remove synthetic state and DB secret, keeping private evidence/backups.
        guest_python("from pathlib import Path\nimport shutil\np=Path("+repr(host)+")\nshutil.rmtree(p/'state',ignore_errors=True)\n(p/'database.env').unlink(missing_ok=True)\n")
        save('cleanup',{'gate':'recovery-cleanup','passed':result['bank_deleted'],'bank_deleted':result['bank_deleted'],'databases_deleted':databases,'role_deleted':role,'evidence_and_backups_retained':True})


if __name__ == '__main__':
    os.umask(0o077)
    try:
        if len(sys.argv)>1 and sys.argv[1] in ('_inside','_canary'):
            if sys.argv[1]=='_inside':inside(sys.argv[2],sys.argv[3])
            else:canary(sys.argv[2])
        else:main()
    except (GateError, AssertionError, KeyError, ValueError) as error:
        # Detailed command logs remain private; never dump environment/arguments.
        print(json.dumps({'passed':False,'error':str(error) if isinstance(error,GateError) else type(error).__name__}))
        raise SystemExit(1)
