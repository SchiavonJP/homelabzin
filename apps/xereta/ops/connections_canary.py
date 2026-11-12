"""Real three-document AFFiNE + SilverBullet canary in a disposable DB/bank.

The supplied private Settings JSON includes the three already-approved import
mappings. All original source reads are allowlisted. Publishing is forbidden.
"""
import json
from pathlib import Path, PurePosixPath
import re
import sys

from sqlalchemy.engine import make_url
from sqlmodel import Session, select
from app import automation as auto, automatic_worker
from app.config import Settings
from app.connections import AffineReader, affine_path, identity, family
from app.db import initialize, make_engine
from app.memory import Memory
from app.models import Artifact, Finding, IntakeNote, IntakeSection, Question, Run, Source, SourceConnection, Version, now
from app.services import execute_run, enqueue
from app.vault import Vault

cfg=Settings(**json.loads(Path(sys.argv[1]).read_text()))
if not re.fullmatch(r'xereta_recovery_[a-f0-9]{12}',make_url(cfg.database_url).database or ''):
    raise SystemExit('disposable_database_required')
if not re.fullmatch(r'knowledge-vault-affine-[a-f0-9]{12}',cfg.hindsight_bank) or cfg.publish_enabled:
    raise SystemExit('isolated_bank_and_no_publishing_required')
if len(cfg.affine_imports)!=3 or len(cfg.affine_workspaces)!=1:
    raise SystemExit('exactly_three_approved_mappings_required')
allowed_paths=set(cfg.affine_imports.values());workspace=cfg.affine_workspaces[0]
allowed_documents={key.split('/')[1] for key in cfg.affine_imports if key.split('/')[0]==workspace}
if len(allowed_documents)!=3:raise SystemExit('invalid_import_mappings')
posts=[]
# Diagnostics stay private and contain counts only, never quotes or note text.
import app.memory as memory_module
original_validation=memory_module.validate_review
validation_diagnostics=[]
def checked_validation(data,sources,versions,trusted):
    try:
        return original_validation(data,sources,versions,trusted)
    except Exception:
        allowed={x.id for x in sources}
        claims=[claim for item in data.get('items',[]) if isinstance(item,dict) for claim in item.get('evidence',[]) if isinstance(claim,dict)] if isinstance(data,dict) and isinstance(data.get('items'),list) else []
        validation_diagnostics.append({'claims':len(claims),'unknown_source_ids':sum(x.get('source_id') not in allowed for x in claims),
            'nonliteral_quotes':sum(x.get('source_id') in versions and isinstance(x.get('quote'),str) and x['quote'] not in versions[x['source_id']].body for x in claims)})
        (cfg.state_path/'validation-diagnostics.json').write_text(json.dumps(validation_diagnostics))
        raise
memory_module.validate_review=checked_validation
class CountingMemory(Memory):
    def call(self,method,path='',body=None,missing=False):
        if method=='POST':posts.append(path)
        return super().call(method,path,body,missing)

class LimitedVault(Vault):
    def inventory(self):return [x for x in super().inventory() if x['path'] in allowed_paths]
    def capture(self,path):
        if path not in allowed_paths:raise RuntimeError('unapproved_source_read_forbidden')
        return super().capture(path)
    def write_review(self,*args,**kwargs):raise RuntimeError('canary_publication_forbidden')
    def write_inbox(self,*args,**kwargs):raise RuntimeError('canary_publication_forbidden')

engine=make_engine(cfg.database_url);cleanup=Memory(cfg)
try:
    initialize(engine,cfg)
    reader=AffineReader(cfg)
    try:inventory=reader.inventory(workspace)
    finally:reader.close()
    exclusions=[identity(x['path'])[1] for x in inventory if identity(x['path'])[1] not in allowed_documents]
    with Session(engine) as s:
        for path in allowed_paths:
            source=Source(path=path,title=PurePosixPath(path).stem,approved=True)
            source.family_id=source.id;s.add(source)
        s.add(SourceConnection(id='affine',workspace=workspace,exclusions=exclusions,approved_at=now(),paused=False));s.commit()
        auto.save_policy(s,'automatic',['space/'],[],6,20,0)
        first=auto.resume(s,cfg,1,'connections-canary-first')['run_id']
    automatic_worker.Vault=LimitedVault;automatic_worker.Memory=CountingMemory
    execute_run(engine,cfg,first)
    with Session(engine) as s:
        job=s.get(Run,first);sources=list(s.exec(select(Source)));versions=list(s.exec(select(Version)))
        items=[*s.exec(select(Finding)),*s.exec(select(Question))]
        evidence=[e for item in items for e in item.evidence]
        by_id={x.id:x for x in sources};by_version={(x.source_id,x.hash):x for x in versions}
        checks={'completed':job.state=='completed','six_source_locations':len(sources)==6,'three_families':len({family(x) for x in sources})==3,
            'three_affine_documents':sum(x.provider=='affine' for x in sources)==3,
            'all_processed':all(x.state=='processed' for x in s.exec(select(IntakeNote))),
            'grounded_citations':bool(evidence) and all(e['quote'] in by_version[e['source_id'],e['version']].body[e['section_start']:e['section_end']] for e in evidence),
            'three_active_questions_max':len(s.exec(select(Question).where(Question.state.in_(['open','answered']))).all())<=3,
            'no_owner_approvals':not any(x.state=='accepted' for x in s.exec(select(Finding))),
            'shared_budget':auto.summary(s,True)['budget']['notes_used']==6,
            'binary_snapshots_preserved':all(any((cfg.state_path/'captures'/x.id).glob('*.bin')) for x in sources if x.provider=='affine')}
        family_count=len({family(x) for x in sources})
        count=(len(versions),len(items),len(posts));first_error=job.error
        second=enqueue(s,'connections-canary-unchanged').id
    execute_run(engine,cfg,second)
    with Session(engine) as s:
        checks['unchanged_rerun_no_duplicate_work']=(len(s.exec(select(Version)).all()),len(s.exec(select(Finding)).all())+len(s.exec(select(Question)).all()),len(posts))==count
        checks['unchanged_rerun_completed']=s.get(Run,second).state=='completed'
        report={'gate':'mixed-affine-silverbullet-real-ingestion','passed':all(checks.values()),'checks':checks,'error':first_error,
                'affine_documents':3,'source_locations':len(sources),'source_families':family_count,
                'sections':len(s.exec(select(IntakeSection)).all()),'citations':len(evidence),'retains_reused':len([u for u in s.exec(select(IntakeSection)) if u.reused_from]),
                'model':cfg.litellm_model,'bank':cfg.hindsight_bank}
        (cfg.state_path/'canary-result.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
        if not report['passed']:raise SystemExit('connections_canary_failed')
finally:
    cleanup.call('DELETE',missing=True);cleanup.close();engine.dispose()
