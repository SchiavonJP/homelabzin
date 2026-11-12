import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlmodel import Session, select

from test_xereta import client, settings, owner, seed
from app import automation as auto
from app.memory import Memory, validate_review
from app.models import (Artifact, AutomationPolicy, AutomationRun, DailyUsage, Feedback, Finding,
                        IntakeNote, IntakeSection, Question, Run, Source, Version)
from app.services import answer_question, enqueue, execute_run, store_review
from app.vault import Capture, DomainError, digest


class VaultFake:
    def __init__(self):
        self.files = {f'space/Personal/{i:02}.md': f'# Note {i}\n\nA source statement {i}.' for i in range(14)}
        self.reads = []
    def inventory(self):
        getattr(self, 'before_request', lambda: None)()
        return [{'path': p, 'size': len(b), 'lastModified': 'same-metadata'} for p, b in self.files.items()]
    def capture(self, path):
        getattr(self, 'before_request', lambda: None)()
        self.reads.append(path)
        if path not in self.files: raise DomainError('vault_file_missing', 404)
        body=self.files[path]
        if not body.strip(): raise DomainError('empty_capture', 422)
        return Capture(path, body, digest(body), '"sha256:' + digest(body) + '"')
    def write_review(self, path, body, etag=None):
        assert path.startswith('space/_AgentKnowledge/'), 'original_note_write_forbidden'
        if etag and self.capture(path).etag != etag:raise DomainError('vault_revision_conflict')
        if not etag and path in self.files:raise DomainError('vault_revision_conflict')
        self.files[path]=body
        return self.capture(path)
    def permalink(self, path): return 'https://silverbullet.joaopaulo.me/' + path
    def close(self): pass


class MemoryFake:
    retain = Memory.retain
    provenance = Memory.provenance
    wait = Memory.wait
    def __init__(self): self.docs={}; self.ops={}; self.posts=[]; self.on_retain=None
    def configure(self, config): pass
    def close(self): pass
    def call(self, method, path='', body=None, missing=False):
        getattr(self, 'before_call', lambda: None)()
        if method == 'POST': self.posts.append((path,body))
        if path == '/memories':
            item=body['items'][0]; oid=body['operation_id']
            assert all(isinstance(value,str) for value in item['metadata'].values())
            self.docs[item['document_id']]={'original_text':item['content'],'document_metadata':item['metadata']}
            self.ops[oid]={'status':'completed'}
            if self.on_retain: self.on_retain()
            return {'success':True,'operation_id':oid}
        if path == '/consolidate':
            oid='consolidate-'+str(len(self.posts)); self.ops[oid]={'status':'completed'}
            return {'operation_id':oid}
        if path.startswith('/operations/'):return self.ops.get(path.rsplit('/',1)[1])
        if path.startswith('/documents/'):return self.docs[path.rsplit('/',1)[1]]
        if path.startswith('/memories/list?'):
            ids=parse_qs(urlsplit(path).query)['document_id']
            return {'items':[{'id':x,'fact_type':'world'} for x in ids if x in self.docs], 'total':len(ids)}
        if path.startswith('/memories/'):return {'document_id':path.rsplit('/',1)[1]}
        raise AssertionError((method,path))


@pytest.fixture
def adapters(monkeypatch, settings):
    vault, memory = VaultFake(), MemoryFake()
    vault.settings = settings
    monkeypatch.setattr('app.automatic_worker.Vault', lambda cfg: vault)
    monkeypatch.setattr('app.automatic_worker.Memory', lambda cfg: memory)
    def synthetic_draft(cfg, sources, versions, trusted):
        return validate_review({'items':[{'issue':'next-action', 'kind':'question', 'text':'Question for '+src.title,
            'reason':'Synthetic fixture.', 'evidence':[{'source_id':src.id, 'quote':versions[src.id].body[:30]}]} for src in sources[:3]]},sources,versions,trusted)
    monkeypatch.setattr('app.automatic_worker.draft',synthetic_draft)
    return vault,memory


def activate(s, settings, notes=10, folders=None):
    settings.acceptance_passed=True
    p=auto.policy(s)
    auto.save_policy(s,'automatic',folders or ['space/Personal/'],[],notes,20,p.revision)
    return auto.resume(s,settings,auto.policy(s).revision,'activate-'+str(auto.policy(s).revision))['run_id']


def test_scope_boundaries_and_preview_never_read_bodies():
    vault=VaultFake()
    vault.files.update({'space/Personality/secret.md':'Secret', 'space/Personal/private/a.md':'Private'})
    result=auto.preview(vault,['space/Personal/'],['space/Personal/private/','space/Personal/00.md'])
    assert result['included']==13 and not vault.reads
    for folders in (['space/../outside/'],['https://evil.invalid/'],['space/.hidden/'],['space/_AgentKnowledge/'],['space//bad/']):
        with pytest.raises(DomainError): auto.preview(vault,folders,[])


def test_owner_only_and_save_does_not_start_or_ingest(client,settings,monkeypatch):
    vault=VaultFake();monkeypatch.setattr('app.main.Vault',lambda cfg:vault)
    reader={'Authorization':'Bearer '+settings.agent_read_token.get_secret_value()}
    for path in ('/automation','/automation/queue','/review-queue?kind=question'):
        assert client.get('/api/v1/xereta'+path,headers=reader).status_code==403
    assert client.post('/api/v1/xereta/automation/preview',headers=reader,json={'folders':[]}).status_code==403
    for action in ('pause','resume'):
        assert client.post('/api/v1/xereta/automation/'+action,headers=reader,json={'expected_revision':0,'idempotency_key':'reader-cannot-control'}).status_code==403
    h=owner(client,settings)
    r=client.put('/api/v1/xereta/automation',headers=h,json={'mode':'automatic','folders':['space/Personal/'],'expected_revision':0})
    assert r.status_code==200 and r.json()['paused'] is True
    with Session(client.app.state.engine) as s:
        assert not s.exec(select(Run)).all() and not s.exec(select(Source)).all()
    assert not vault.reads
    assert client.post('/api/v1/xereta/automation/resume',headers=h,json={'expected_revision':1,'idempotency_key':'blocked-by-gates'}).status_code==409
    assert client.put('/api/v1/xereta/automation',headers=h,json={'mode':'automatic','folders':[],'expected_revision':1}).status_code==422


def test_resume_idempotency_pause_and_revision(client,settings):
    with Session(client.app.state.engine) as s:
        rid=activate(s,settings)
        rev=auto.policy(s).revision
        same=auto.resume(s,settings,rev-1,'activate-'+str(rev-1))
        assert same['run_id']==rid and len(s.exec(select(Run)).all())==1
        with pytest.raises(DomainError,match='automation_run_active'):
            auto.save_policy(s,'manual',[],[],10,20,rev)
        auto.pause(s,rev)
        assert s.get(Run,rid).state=='stopped'
        assert auto.policy(s).paused
        with pytest.raises(DomainError,match='automation_revision_conflict'):
            auto.resume(s,settings,0,'stale-key')


def test_automatic_rotation_quota_and_persistent_question_queue(client,settings,adapters):
    vault,memory=adapters
    with Session(client.app.state.engine) as s: rid=activate(s,settings)
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        run=s.get(Run,rid)
        assert run.state=='completed',run.error
        assert len(s.exec(select(Source)).all())==10
        assert len(s.get(DailyUsage,auto.day_key()).notes)==10
        assert len(s.exec(select(Question).where(Question.state=='open')).all())==3
        assert len(s.exec(select(Question).where(Question.state=='queued')).all())==7
        assert len(s.exec(select(IntakeNote).where(IntakeNote.state=='processed')).all())==10
        assert len(s.exec(select(IntakeNote).where(IntakeNote.state=='unread')).all())==4
        q=s.exec(select(Question).where(Question.state=='open')).first()
        answer_question(s,q.id,'Owner reply.','confirmed',q.revision)
        assert len(s.exec(select(Question).where(Question.state=='open')).all())==3
        second=enqueue(s,'second-window');second_id=second.id
    retains=len([p for p,_ in memory.posts if p=='/memories'])
    execute_run(client.app.state.engine,settings,second_id)
    with Session(client.app.state.engine) as s:
        # Owner feedback is independent of the ten-original-note limit.
        assert len(s.get(DailyUsage,auto.day_key()).notes)==10
        assert len(s.exec(select(Source).where(Source.path.startswith('space/'))).all())==10
    assert len([p for p,_ in memory.posts if p=='/memories'])==retains+1


def test_long_note_exact_coverage_and_original_citations(client,settings,adapters):
    vault,memory=adapters
    body=('A long original paragraph.\n\n'*1100)+'THE END'
    vault.files={'space/Personal/long.md':body}
    with Session(client.app.state.engine) as s: rid=activate(s,settings)
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        run=s.get(Run,rid);assert run.state=='completed',run.error
        src=s.exec(select(Source)).one();v=s.exec(select(Version)).one()
        units=s.exec(select(IntakeSection).order_by(IntakeSection.number)).all()
        assert len(units)>2 and all(x.state=='reviewed' for x in units)
        assert ''.join(v.body[u.start:u.end] for u in units)==body
        assert all(u.end-u.start<=12000 for u in units)
        assert v.body==body and len(s.get(DailyUsage,auto.day_key()).notes)==1
        for q in s.exec(select(Question)):
            for e in q.evidence:
                assert e['source_id']==src.id and e['version']==v.hash and e['quote'] in body[e['section_start']:e['section_end']]
        assert vault.files=={'space/Personal/long.md':body}


def test_pause_after_retain_resumes_without_second_retain(client,settings,adapters):
    vault,memory=adapters;vault.files={'space/Personal/only.md':'A note for recovery.'}
    with Session(client.app.state.engine) as s: rid=activate(s,settings)
    def pause():
        memory.on_retain=None
        with Session(client.app.state.engine) as s:auto.pause(s,auto.policy(s).revision)
    memory.on_retain=pause
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).error=='automation_paused'
        oid=s.exec(select(IntakeSection)).one().operation_id
        resumed=auto.resume(s,settings,auto.policy(s).revision,'resume-after-pause')['run_id']
    execute_run(client.app.state.engine,settings,resumed)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,resumed).state=='completed',s.get(Run,resumed).error
        assert s.exec(select(IntakeSection)).one().operation_id==oid
    assert len([p for p,_ in memory.posts if p=='/memories'])==1


def test_budget_charge_is_once_and_recovery_does_not_reset(client,settings):
    at=datetime(2026,11,6,23,59,tzinfo=UTC)
    with Session(client.app.state.engine) as s:
        rid=activate(s,settings)
        run=s.get(Run,rid);run.started_at=at.isoformat();s.add(run);s.commit()
        assignment=s.get(AutomationRun,rid)
        auto.begin_run(s,run,assignment,at)
        auto.charge_run(s,run,assignment,at+timedelta(minutes=35))
        auto.charge_run(s,run,assignment,at+timedelta(minutes=50))
        assert assignment.charged_seconds==1200
        assert s.get(DailyUsage,auto.day_key(at)).seconds==1200
        assert auto.budget(s,auto.policy(s),at)['seconds_remaining']==0
        assert auto.budget(s,auto.policy(s),at+timedelta(days=1))['seconds_remaining']==1200
        assert auto.day_key(datetime(2026,11,7,2,59,tzinfo=UTC))=='2026-11-06'
        assert auto.day_key(datetime(2026,11,7,3,0,tzinfo=UTC))=='2026-11-07'


def test_one_bad_file_does_not_block_other_notes(client,settings,adapters):
    vault,memory=adapters
    vault.files={'space/Personal/a.md':'', 'space/Personal/b.md':'A valid statement.', 'space/Personal/generated.md':'---\ngenerated: true\n---\nGenerated.'}
    with Session(client.app.state.engine) as s:rid=activate(s,settings)
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).state=='completed',s.get(Run,rid).error
        assert s.get(IntakeNote,'space/Personal/a.md').state=='failed'
        assert s.get(IntakeNote,'space/Personal/b.md').state=='processed'
        assert s.get(IntakeNote,'space/Personal/generated.md').state=='excluded'
        assert len(s.exec(select(Source)).all())==1


def test_metadata_miss_is_caught_by_weekly_audit(client,settings,adapters):
    vault,memory=adapters;vault.files={'space/Personal/a.md':'AAAA'}
    with Session(client.app.state.engine) as s:rid=activate(s,settings)
    execute_run(client.app.state.engine,settings,rid)
    vault.files['space/Personal/a.md']='BBBB'
    with Session(client.app.state.engine) as s:
        note=s.get(IntakeNote,'space/Personal/a.md')
        note.verified_at=(auto.instant()-timedelta(days=8)).isoformat();s.add(note);s.commit()
        rid=enqueue(s,'audit-window').id
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).state=='completed',s.get(Run,rid).error
        assert s.exec(select(Source)).one().version==digest('BBBB')
        assert len(s.exec(select(Version)).all())==2


def test_provenance_uses_document_filter_and_pagination(settings):
    import httpx
    seen=[]
    source=Source(path='space/a.md',title='a',version='v',approved=True)
    def handler(request):
        seen.append(str(request.url))
        if '/documents/' in request.url.path:return httpx.Response(200,json={'document_metadata':{'version':'v','source_id':source.id}})
        if request.url.path.endswith('/memories/list'):
            assert request.url.params['document_id']==source.id
            if request.url.params['offset']=='0':return httpx.Response(200,json={'items':[{'id':str(i),'fact_type':'observation'} for i in range(100)],'total':101})
            return httpx.Response(200,json={'items':[{'id':'raw','fact_type':'world'}],'total':101})
        return httpx.Response(200,json={'document_id':source.id})
    memory=Memory(settings,httpx.MockTransport(handler))
    assert memory.provenance([source])=={source.id}
    assert any('offset=100' in url for url in seen)
    memory.close()


def test_review_history_pagination(client,settings):
    with Session(client.app.state.engine) as s:
        for i in range(45):s.add(Finding(key=str(i),kind='finding',text=str(i),reason='Fixture'))
        s.commit()
    h=owner(client,settings)
    first=client.get('/api/v1/xereta/review-queue?kind=finding&limit=20',headers=h)
    second=client.get('/api/v1/xereta/review-queue?kind=finding&limit=20&offset=20',headers=h)
    assert first.status_code==second.status_code==200
    assert first.json()['total']==45
    assert not {x['id'] for x in first.json()['items']}.intersection(x['id'] for x in second.json()['items'])


def test_migration_adopts_existing_0002_without_changing_reviews(settings):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    from app.db import make_engine, initialize
    engine=make_engine(settings.database_url)
    cfg=Config();cfg.set_main_option('script_location',str(Path(__file__).parents[1]/'app/migrations'))
    with engine.begin() as connection:
        cfg.attributes['connection']=connection;command.upgrade(cfg,'0002')
    # Seed the actual old schema, without using new ORM columns against it.
    from sqlalchemy import MetaData, select as sql_select
    source=Source(path='space/Projeto.md',title='Projeto',approved=True,version=digest('Guardar 14 dias.'))
    version=Version(source_id=source.id,hash=source.version,body='Guardar 14 dias.',etag='')
    q=Question(issue='retention',text='Qual prazo vale?',reason='Conflito',evidence=[{'source_id':source.id,'version':version.hash,'quote':'Guardar 14 dias.'}])
    metadata=MetaData();metadata.reflect(bind=engine)
    expected={}
    with engine.begin() as connection:
        for obj in (source,version,q):
            table=metadata.tables[obj.__tablename__]
            values={key:value for key,value in obj.model_dump().items() if key in table.c}
            connection.execute(table.insert(),values)
            expected[table.name]=values
    initialize(engine,settings)
    with engine.connect() as connection:
        for name,values in expected.items():
            assert dict(connection.execute(sql_select(metadata.tables[name])).first()._mapping)==values
    with Session(engine) as s:
        restored=s.get(Source,source.id)
        assert restored.family_id==source.id and restored.external_id==source.path
        assert not s.get(AutomationPolicy,1)
        assert auto.policy(s).mode=='manual' and auto.policy(s).paused
    engine.dispose()


def test_exhausted_budget_resume_never_allocates_another_run(client,settings):
    with Session(client.app.state.engine) as s:
        rid=activate(s,settings)
        auto.pause(s,auto.policy(s).revision)
        s.add(DailyUsage(day=auto.day_key(),seconds=1200));s.commit()
        result=auto.resume(s,settings,auto.policy(s).revision,'resume-exhausted')
        assert result['state']=='waiting_budget' and result['run_id'] is None
        assert len(s.exec(select(Run)).all())==1
        assert not auto.policy(s).paused
        with pytest.raises(DomainError,match='automation_daily_budget_exhausted'):enqueue(s,'cannot-override')


def test_paused_schedule_consumes_slot_without_reading(client,settings):
    from app.services import due_schedule
    from app.models import Schedule
    with Session(client.app.state.engine) as s:
        settings.acceptance_passed=True
        auto.save_policy(s,'automatic',['space/Personal/'],[],10,20,0)
        schedule=s.get(Schedule,1);schedule.enabled=True;s.add(schedule);s.commit()
        assert due_schedule(s,settings,datetime(2026,11,6,10,0,tzinfo=UTC)) is None
        assert s.get(Schedule,1).last_due=='2026-11-06T03:00:00-03:00'
        assert not s.exec(select(Run)).all()


def test_chunk_quote_cannot_cite_text_from_another_section(client,settings):
    from app.automatic_worker import views
    with Session(client.app.state.engine) as s:
        body='A'*12000+'Unique second section.'
        source=Source(path='space/Personal/long.md',title='Long',approved=True,version=digest(body));s.add(source)
        version=Version(source_id=source.id,hash=source.version,body=body,etag='');s.add(version);s.commit()
        units=auto.ensure_sections(s,source,version)
        sources,versions,_=views(s,[units[0]])
        with pytest.raises(DomainError,match='quotation_or_provenance_invalid'):
            validate_review({'items':[{'issue':'forged','kind':'finding','text':'Forged','reason':'Fixture','evidence':[{'source_id':units[0].id,'quote':'Unique second section.'}]}]},sources,versions,{units[0].id})


def test_unchanged_rerun_does_not_retain_or_draft_again(client,settings,adapters):
    vault,memory=adapters;vault.files={'space/Personal/a.md':'A stable original note.'}
    with Session(client.app.state.engine) as s:rid=activate(s,settings)
    execute_run(client.app.state.engine,settings,rid)
    count=len(memory.posts)
    with Session(client.app.state.engine) as s:rid=enqueue(s,'unchanged-rerun').id
    execute_run(client.app.state.engine,settings,rid)
    assert len(memory.posts)==count
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).state=='completed'
        assert len(s.exec(select(Source)).all())==len(s.exec(select(Version)).all())==1


def test_missing_file_keeps_snapshot_and_future_note_is_discovered(client,settings,adapters):
    vault,memory=adapters;vault.files={'space/Personal/a.md':'Original.'}
    with Session(client.app.state.engine) as s:rid=activate(s,settings)
    execute_run(client.app.state.engine,settings,rid)
    vault.files={'space/Personal/new.md':'Future note.'}
    with Session(client.app.state.engine) as s:rid=enqueue(s,'future-and-missing').id
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).state=='completed',s.get(Run,rid).error
        assert s.get(IntakeNote,'space/Personal/a.md').state=='missing'
        missing=s.exec(select(Source).where(Source.path=='space/Personal/a.md')).one()
        assert missing.error=='source_missing_no_automatic_deletion'
        old_question=next(q for q in s.exec(select(Question)) if q.evidence[0]['source_id']==missing.id)
        with pytest.raises(DomainError,match='question_evidence_changed'):
            answer_question(s,old_question.id,'Cannot confirm stale evidence.','confirmed',old_question.revision)
        answer_question(s,old_question.id,'','deferred',old_question.revision)
        assert old_question.state=='deferred'
        assert s.get(IntakeNote,'space/Personal/new.md').state=='processed'
        assert len(s.exec(select(Version)).all())==2


@pytest.mark.parametrize('point',['retain-accepted','draft-saved'])
def test_automatic_process_death_reuses_remote_work(tmp_path,point):
    import os
    from app.db import make_engine
    from recovery_support import Backend, setup_case, run_state
    from automatic_support import AutomaticProcess
    cfg, old=setup_case(tmp_path,os.environ.get('XERETA_RECOVERY_DATABASE_URL'))
    cfg.acceptance_passed=True;cfg.publish_enabled=False
    engine=make_engine(cfg.database_url)
    try:
        with Session(engine) as s:
            s.delete(s.get(Run,old));s.commit();rid=activate(s,cfg,folders=['space/'])
        first=AutomaticProcess(cfg,point)
        try:first.barrier(seconds=60)
        finally:first.kill()
        before=run_state(cfg,rid)
        replacement=AutomaticProcess(cfg)
        try:replacement.finish(seconds=90)
        finally:replacement.kill()
        result=run_state(cfg,rid)
        assert result['state']=='completed',result
        assert result['started_at']==before['started_at']
        calls=Backend(cfg.state_path).rows('calls')
        assert len([x for x in calls if x['method']=='POST' and x['path']=='/memories'])==1
        assert len([x for x in calls if x['method']=='DRAFT'])==1
        with Session(engine) as s:
            assert s.exec(select(AutomationRun)).one().accounted
            assert s.exec(select(IntakeNote)).one().state=='processed'
            assert len(s.exec(select(Finding)).all())==1
    finally:engine.dispose()


def test_postgresql_resume_controls_serialize_with_policy_changes(tmp_path):
    import os, threading
    from sqlalchemy import text
    from app.db import make_engine
    from recovery_support import setup_case
    url=os.environ.get('XERETA_RECOVERY_DATABASE_URL')
    if not url:pytest.skip('operator supplies disposable PostgreSQL database')
    cfg,old=setup_case(tmp_path,url);cfg.acceptance_passed=True
    engine=make_engine(cfg.database_url)
    ready,done=threading.Event(),threading.Event();result=[]
    try:
        with Session(engine) as s:
            s.delete(s.get(Run,old));s.commit()
            auto.save_policy(s,'automatic',['space/Personal/'],[],10,20,0)
        def resume():
            try:
                with Session(engine) as s:ready.set();auto.resume(s,cfg,1,'concurrent-resume')
            except DomainError as error:result.append(error.code)
            finally:done.set()
        with Session(engine) as s:
            s.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':1481855590})
            thread=threading.Thread(target=resume,daemon=True);thread.start()
            assert ready.wait(5) and not done.wait(.2)
            auto.save_policy(s,'manual',[],[],10,20,1)
            assert done.wait(10);thread.join(5)
        assert result==['automation_revision_conflict']
        with Session(engine) as s:assert not s.exec(select(Run)).all()
    finally:engine.dispose()


def test_section_completion_and_parent_progress_commit_together(client,settings,adapters):
    from sqlalchemy import event
    vault,memory=adapters;vault.files={'space/Personal/a.md':'An original statement.'}
    with Session(client.app.state.engine) as s:rid=activate(s,settings)
    def inspect_commit(s):
        if s.bind is not client.app.state.engine:return
        for note in s.exec(select(IntakeNote).where(IntakeNote.state=='partial')):
            units=s.exec(select(IntakeSection).where(IntakeSection.source_id==note.source_id,IntakeSection.version==note.version)).all()
            assert not units or not all(x.state=='reviewed' for x in units), 'partial_parent_cannot_commit_with_all_sections_complete'
    event.listen(Session,'before_commit',inspect_commit)
    try:execute_run(client.app.state.engine,settings,rid)
    finally:event.remove(Session,'before_commit',inspect_commit)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).state=='completed',s.get(Run,rid).error
        assert s.exec(select(IntakeNote)).one().state=='processed'


def test_vault_checkbox_answer_is_ingested_in_same_automatic_window(client,settings,adapters):
    from app.review import ANSWER_START,ANSWER_END,CHECKS,question_path
    vault,memory=adapters
    original='An original personal statement.'
    vault.files={'space/Personal/a.md':original};settings.publish_enabled=True
    with Session(client.app.state.engine) as s:rid=activate(s,settings)
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).state=='completed',s.get(Run,rid).error
        q=s.exec(select(Question)).one();qid=q.id;path=question_path(q)
    vault.files[path]=vault.files[path].replace(ANSWER_START+'\n\n'+ANSWER_END,ANSWER_START+'\nOwner answer from Obsidian.\n'+ANSWER_END).replace('- [ ] '+CHECKS['confirm'],'- [x] '+CHECKS['confirm'])
    with Session(client.app.state.engine) as s:rid=enqueue(s,'collect-vault-feedback').id
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).state=='completed',s.get(Run,rid).error
        assert s.get(Question,qid).answer=='Owner answer from Obsidian.'
        feedback=s.exec(select(Feedback)).one()
        assert feedback.origin=='vault' and feedback.state=='complete'
        source=s.exec(select(Source).where(Source.path.startswith('feedback:'))).one()
        assert source.state=='complete'
    assert vault.files['space/Personal/a.md']==original
    assert len([p for p,_ in memory.posts if p=='/memories'])==2


def test_oversized_file_is_held_without_downloading_body(client,settings,adapters):
    vault,memory=adapters
    vault.inventory=lambda:[{'path':'space/Personal/huge.md','size':9*1024*1024}]
    vault.capture=lambda path:(_ for _ in ()).throw(AssertionError('oversized_body_must_not_be_read'))
    with Session(client.app.state.engine) as s:rid=activate(s,settings)
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).state=='completed',s.get(Run,rid).error
        note=s.get(IntakeNote,'space/Personal/huge.md')
        assert note.state=='failed' and note.error=='capture_too_large'
        assert not s.exec(select(Source)).first()


@pytest.mark.parametrize('target',['/memories','/consolidate'])
def test_pause_before_http_post_keeps_work_resumable(client,settings,adapters,target):
    vault,memory=adapters;vault.files={'space/Personal/a.md':'An original statement.'}
    with Session(client.app.state.engine) as s:rid=activate(s,settings)
    actual=memory.call
    paused=[]
    def before_post(method,path='',body=None,missing=False):
        if method=='POST' and path==target and not paused:
            paused.append(True)
            with Session(client.app.state.engine) as s:auto.pause(s,auto.policy(s).revision)
        return actual(method,path,body,missing)
    memory.call=before_post
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).error=='automation_paused'
        rid=auto.resume(s,settings,auto.policy(s).revision,'resume-before-post-'+target[1:])['run_id']
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).state=='completed',s.get(Run,rid).error
        assert s.exec(select(IntakeNote)).one().state=='processed'
        assert not s.exec(select(IntakeSection).where(IntakeSection.state=='held')).first()
    assert len([p for p,_ in memory.posts if p=='/memories'])==1
    assert len([p for p,_ in memory.posts if p=='/consolidate'])==1
