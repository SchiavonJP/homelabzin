"""Disposable Automatic mode + real Hindsight/model gate. Never uses the real vault.

Run with a private JSON Settings file, a disposable recovery DB and isolated
knowledge-vault-auto-* bank. Prints counts and booleans, never credentials.
"""
import json
from pathlib import Path
import sys

from sqlmodel import Session, select
from app import automation, automatic_worker
from app.config import Settings
from app.db import initialize, make_engine
from app.memory import Memory
from app.models import Finding, IntakeNote, IntakeSection, Question, Run, Source, Version
from app.services import execute_run
from app.vault import Capture, digest

payload=json.loads(Path(sys.argv[1]).read_text())
cfg=Settings(**payload)
from sqlalchemy.engine import make_url
import re
if not re.fullmatch('xereta_recovery_[a-f0-9]{12}',make_url(cfg.database_url).database or ''):
    raise SystemExit('disposable_database_required')
if not re.fullmatch('knowledge-vault-auto-[a-f0-9]{12}',cfg.hindsight_bank):
    raise SystemExit('isolated_bank_required')
if cfg.publish_enabled:raise SystemExit('canary_publication_must_be_disabled')
BODY=('# Synthetic automatic qualification note\n\nProject Moss snapshots stay local. '
      'One source reports a retention of 14 days. The discrepancy remains unresolved.\n\n'
      + ('This is synthetic qualification material; it describes the same Project Moss, not independent evidence.\n\n'*125)
      + 'A conflicting statement reports 30 days for Project Moss snapshots. No owner resolution was supplied.\n')
PATH='space/AutomaticGate/long-note.md'
class SyntheticVault:
    settings=cfg
    def inventory(self):
        getattr(self,'before_request',lambda:None)()
        return [{'path':PATH,'size':len(BODY),'lastModified':'synthetic-fixed'}]
    def capture(self,path):
        getattr(self,'before_request',lambda:None)()
        if path!=PATH:raise RuntimeError('real_vault_access_forbidden')
        return Capture(path,BODY,digest(BODY),'"sha256:'+digest(BODY)+'"')
    def permalink(self,path):return 'https://example.invalid/synthetic-automatic-note'
    def close(self):pass

engine=make_engine(cfg.database_url)
cleanup=Memory(cfg)
try:
    initialize(engine,cfg)
    automatic_worker.Vault=lambda settings:SyntheticVault()
    with Session(engine) as s:
        automation.save_policy(s,'automatic',['space/AutomaticGate/'],[],1,20,0)
        rid=automation.resume(s,cfg,1,'canary-automatic-start')['run_id']
    execute_run(engine,cfg,rid)
    with Session(engine) as s:
        run=s.get(Run,rid);source=s.exec(select(Source)).one();version=s.exec(select(Version)).one()
        sections=s.exec(select(IntakeSection).order_by(IntakeSection.number)).all()
        evidence=[e for x in [*s.exec(select(Question)),*s.exec(select(Finding))] for e in x.evidence]
        checks={'completed':run.state=='completed','multiple_sections':len(sections)>=2,
            'all_sections_reviewed':all(x.state=='reviewed' for x in sections),
            'full_source_preserved':version.body==BODY,
            'exact_coverage':''.join(BODY[x.start:x.end] for x in sections)==BODY,
            'one_original':len(s.exec(select(Source)).all())==1,
            'processed_progress':s.exec(select(IntakeNote)).one().state=='processed',
            'citations_present':bool(evidence),
            'citations_grounded':all(e['source_id']==source.id and e['version']==version.hash and e['quote'] in BODY[e['section_start']:e['section_end']] for e in evidence),
            'proposals_not_owner_approvals':not s.exec(select(Finding).where(Finding.state=='accepted')).first()}
        report={'gate':'automatic-real-hindsight-model','passed':all(checks.values()),'checks':checks,
                'sections':len(sections),'section_states':[{'state':x.state,'error':x.error} for x in sections],'citations':len(evidence),'error':run.error,'bank':cfg.hindsight_bank}
        Path('/data/canary-result.json').write_text(json.dumps(report))
        print(json.dumps(report))
        if not report['passed']:raise SystemExit('automatic_canary_failed')
finally:
    cleanup.call('DELETE',missing=True)
    cleanup.close();engine.dispose()
