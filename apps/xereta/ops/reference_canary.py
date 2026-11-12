"""Real model/Hindsight qualification using synthetic readiness in an isolated DB/bank."""
import json
import re
import sys
from pathlib import Path
from sqlalchemy.engine import make_url
from sqlmodel import Session,select
from app.config import Settings
from app.db import make_engine,initialize
from app import references,library_config,automation,automatic_worker
from app.memory import Memory
from app.models import ReferenceItem,ReferenceCapture,Source,Version,Finding,Question,Run
from app.services import enqueue

cfg=Settings(**json.loads(Path(sys.argv[1]).read_text()))
if not re.fullmatch(r'xereta_recovery_[a-f0-9]{12}',make_url(cfg.database_url).database or ''):raise SystemExit('disposable_database_required')
if not re.fullmatch(r'knowledge-vault-library-[a-f0-9]{12}',cfg.hindsight_bank) or cfg.publish_enabled:raise SystemExit('isolated_bank_required')
if cfg.litellm_model!='generalist':raise SystemExit('generalist_required')
posts=[]
class CountingMemory(Memory):
    def call(self,method,path='',body=None,missing=False):
        if method=='POST':posts.append(path)
        return super().call(method,path,body,missing)
class NoVault:
    def __init__(self,settings):self.settings=settings
    def inventory(self):return []
    def capture(self,path):raise RuntimeError('canary_original_read_forbidden')
    def close(self):pass
    def permalink(self,path):return 'https://example.org/fixture'

engine=make_engine(cfg.database_url);cleanup=Memory(cfg)
try:
    initialize(engine,cfg)
    with Session(engine) as s:
        data=library_config.current(s).model_dump();data['ingestion_paused']=False
        library_config.save(s,data,0)
        unread=references.item_url(s,'https://example.org/unread-fixture','Unread article about agents')
        tool=references.item_url(s,'https://github.com/example/fixture','Repository reference, not reviewed')
        ready=references.item_url(s,'https://example.org/read-fixture','Cedar retention conflict — synthetic qualification')
        s.commit();s.refresh(unread);s.refresh(tool);s.refresh(ready)
        counts=(len(s.exec(select(Source)).all()),len(posts))
        references.organize_one(s,cfg,unread,library_config.current(s))
        assert (len(s.exec(select(Source)).all()),len(posts))==counts
        capture=references.save_capture(s,ready,{'url':ready.url,'title':ready.title,'body':
            'This synthetic article states that Project Cedar keeps local snapshots for 14 days. '
            'Another paragraph reports retention of 30 days. The discrepancy is explicitly unresolved. '
            'Cloud backup is only an author suggestion. The owner has not approved that suggestion.'})
        references.approve(s,cfg,ready.id,capture['capture']['hash'],capture['item']['revision'])
        ready.approval_origin='isolated-test-fixture';s.add(ready);s.commit()
        ready_id=ready.id
        automation.save_policy(s,'automatic',['space/Referências/'],[],3,20,0)
        first=automation.resume(s,cfg,1,'reference-canary-first')['run_id']
    automatic_worker.Vault=NoVault;automatic_worker.Memory=CountingMemory
    automatic_worker.execute(engine,cfg,first)
    with Session(engine) as s:
        job=s.get(Run,first)
        if job.state!='completed':
            print(json.dumps({'passed':False,'stage':job.stage,'error':job.error}));raise SystemExit(1)
        sources=s.exec(select(Source)).all();versions=s.exec(select(Version)).all()
        assert len(sources)==1 and sources[0].path=='reference:'+ready_id
        items=[*s.exec(select(Finding)),*s.exec(select(Question))]
        evidence=[x for row in items for x in row.evidence]
        by_version={(x.source_id,x.hash):x for x in versions}
        assert evidence and all(x['quote'] in by_version[x['source_id'],x['version']].body for x in evidence)
        assert not any(x.state=='accepted' for x in s.exec(select(Finding)))
        first_counts=(len(sources),len(versions),len(items),len(posts))
        second=enqueue(s,'reference-canary-unchanged').id
    automatic_worker.execute(engine,cfg,second)
    with Session(engine) as s:
        assert s.get(Run,second).state=='completed'
        assert first_counts==(len(s.exec(select(Source)).all()),len(s.exec(select(Version)).all()),
            len(s.exec(select(Finding)).all())+len(s.exec(select(Question)).all()),len(posts))
        assert len(s.exec(select(Question).where(Question.state.in_(['open','answered']))).all())<=3
        assert automation.summary(s,True)['budget']['notes_used']==1
    reflected=cleanup.call('POST','/reflect',{'query':'Which Cedar retention values are reported, and is the conflict resolved? Preserve uncertainty.','budget':'low','max_tokens':400,'include':{'facts':{}},'fact_types':['world','experience','observation']})
    assert isinstance(reflected,dict) and bool(reflected)
    report={'gate':'reference-readiness-generalist-real-hindsight','passed':True,'synthetic_readiness':True,
        'model':cfg.litellm_model,'catalogue_items':3,'retained_sources':1,'unread_retention_calls':0,
        'grounded_citations':len(evidence),'unchanged_rerun_no_duplicate_work':True,'shared_budget':True,
        'metadata_organization_no_hindsight_calls':True,'reflect_completed':True,'owner_knowledge_approvals':0}
    Path('/data/reference-canary-result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    cleanup.call('DELETE',missing=True);cleanup.close();engine.dispose()
