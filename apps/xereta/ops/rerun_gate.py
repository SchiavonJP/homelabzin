"""Queue and qualify an unchanged rerun. Run inside app; no synthetic owner feedback."""
import json,time
from sqlmodel import Session,select
from app.config import Settings
from app.db import make_engine
from app.models import Source,Version,Question,Finding,Run,Publication,Feedback
from app.services import enqueue
from uuid import uuid4
cfg=Settings();engine=make_engine(cfg.database_url)
def snapshot(s):
 return {'sources':[(x.id,x.version) for x in s.exec(select(Source).order_by(Source.id))],
         'versions':[(x.source_id,x.hash,x.operation_id) for x in s.exec(select(Version).order_by(Version.id))],
         'questions':[(x.id,x.revision,x.state,x.disposition,x.answer) for x in s.exec(select(Question).order_by(Question.id))],
         'findings':[(x.id,x.revision,x.state) for x in s.exec(select(Finding).order_by(Finding.id))],
         'feedback':[(x.id,x.state,x.disposition,x.answer) for x in s.exec(select(Feedback).order_by(Feedback.id))]}
with Session(engine) as s:
 before=snapshot(s);job=enqueue(s,'rerun-gate:'+str(uuid4()));jid=job.id
for _ in range(60):
 time.sleep(2)
 with Session(engine) as s:
  job=s.get(Run,jid)
  if job.state in ('completed','failed','stopped'):
   after=snapshot(s)
   checks={'completed':job.state=='completed','unchanged_state':before==after,'published':s.get(Publication,1).state=='published'}
   print(json.dumps({'gate':'unchanged-rerun','run_id':jid,'passed':all(checks.values()),'checks':checks,
      'counts':{k:len(v) for k,v in after.items()},'error':job.error}))
   if not all(checks.values()):raise SystemExit(1)
   break
else:raise SystemExit('rerun_gate_timeout')
