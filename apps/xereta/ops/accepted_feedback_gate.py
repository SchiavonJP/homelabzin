"""Check that real question answers and finding approvals reach Hindsight unchanged."""
import argparse
import json
from sqlmodel import Session,select
from app.config import Settings
from app.db import make_engine
from app.memory import Memory
from app.models import Feedback,Finding,Question,Run,Schedule,Source,Version
from app.review import question_path,finding_path,answer,checkbox
from app.services import enqueue,save_private
from app.vault import Vault,digest

parser=argparse.ArgumentParser()
parser.add_argument('phase',choices=['start','verify'])
args=parser.parse_args()
cfg=Settings();engine=make_engine(cfg.database_url)
path=cfg.state_path/'gates'/'accepted-feedback.json'

def questions(s):
 return {q.id:{'state':q.state,'revision':q.revision,'answer_sha256':digest(q.answer),'disposition':q.disposition}
         for q in s.exec(select(Question))}

def findings(s):
 return {f.id:{'state':f.state,'revision':f.revision} for f in s.exec(select(Finding).where(Finding.state.in_(['accepted','rejected'])))}

def original_heads(s):
 return {x.id:x.version for x in s.exec(select(Source).where(Source.path.startswith('space/')))}

with Session(engine) as s:
 if args.phase=='start':
  pending=sorted(f.id for f in s.exec(select(Feedback).where(Feedback.state=='pending',Feedback.disposition!='deferred')))
  if not pending:
   print(json.dumps({'status':'nothing_pending'}));raise SystemExit(0)
  before={'feedback_ids':pending,'questions':questions(s),'findings':findings(s),'original_heads':original_heads(s)}
  job=enqueue(s,'accepted-feedback:'+digest(json.dumps(pending)))
  before['run_id']=job.id
  save_private(path,json.dumps(before))
  print(json.dumps({'status':'queued','pending_feedback':len(pending),'run_id':job.id}))
 else:
  before=json.loads(path.read_text());job=s.get(Run,before['run_id'])
  if job.state in ('queued','running'):
   print(json.dumps({'status':'pending','stage':job.stage,'run_id':job.id}));raise SystemExit(2)
  vault=Vault(cfg);memory=Memory(cfg)
  retained=True
  for fid in before['feedback_ids']:
   fb=s.get(Feedback,fid)
   src=s.exec(select(Source).where(Source.path=='feedback:'+fb.question_id)).one()
   version=s.exec(select(Version).where(Version.source_id==src.id,Version.hash==src.version)).one()
   retained=retained and fb.state=='complete' and version.state=='complete'
   if version.state=='complete':memory.verify(src,version)
  checks={'run_completed':job.state=='completed','owner_feedback_retained_and_verified':retained,
   'answers_and_revisions_preserved':all(questions(s).get(k)==v for k,v in before['questions'].items()),
   'approved_or_rejected_findings_preserved':all(findings(s).get(k)==v for k,v in before['findings'].items()),
   'original_note_versions_unchanged':original_heads(s)==before['original_heads'],
   'answers_published':all(answer(vault.capture(question_path(q)).body)==q.answer for q in s.exec(select(Question))),
   'accepted_findings_published':all(checkbox(vault.capture(finding_path(f)).body,'approve' if f.kind=='decision' else 'accept')
       for f in s.exec(select(Finding).where(Finding.state=='accepted'))),
   'schedule_disabled':not s.get(Schedule,1).enabled}
  print(json.dumps({'gate':'accepted-owner-feedback','passed':all(checks.values()),'checks':checks,
                   'run_id':job.id,'feedback_records_verified':len(before['feedback_ids']),'error':job.error}))
  if not all(checks.values()):raise SystemExit(1)
