"""Qualify a real owner response without inventing one or printing private content.

Run inside Xereta: --start queues a bounded digest; --verify checks its result.
The private baseline stays in /data/gates. Original note changes fail the gate.
"""
import argparse
import json
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session, select
from app.config import Settings
from app.db import make_engine
from app.memory import Memory
from app.models import Artifact, Feedback, Finding, Publication, Question, Run, Schedule, Source, Version
from app.services import BEGIN, END, answers_from, enqueue, save_private
from app.vault import Vault, INBOX, digest

parser=argparse.ArgumentParser()
parser.add_argument('phase',choices=['start','verify'])
args=parser.parse_args()
cfg=Settings();engine=make_engine(cfg.database_url)
path=cfg.state_path/'gates'/'owner-feedback.json'

def outside(body):
    if body.count(BEGIN)!=1 or body.count(END)!=1:
        raise SystemExit('inbox_markers_invalid')
    return digest(body.split(BEGIN)[0]),digest(body.split(END)[1])

def originals(s):
    return {x.id:x.version for x in s.exec(select(Source).where(Source.path.startswith('space/')))}

with Session(engine) as s:
    if args.phase=='start':
        if path.exists():
            baseline=json.loads(path.read_text())
            print(json.dumps({'status':'already_started','run_id':baseline['run_id']}))
            raise SystemExit(0)
        fb=s.exec(select(Feedback).where(Feedback.origin.in_(['web','vault']),Feedback.disposition!='deferred').order_by(Feedback.created_at.desc())).first()
        if not fb:
            raise SystemExit('real_owner_answer_required')
        q=s.get(Question,fb.question_id)
        if not q or q.answer!=fb.answer:
            raise SystemExit('question_answer_mismatch')
        vault=Vault(cfg)
        incoming=vault.capture(INBOX)
        vault.close()
        before={
            'feedback_id':fb.id,'question_id':q.id,'answer_sha256':digest(fb.answer),
            'disposition':fb.disposition,'question_revision':q.revision,'originals':originals(s),
            'outside':outside(incoming.body),
            'accepted_decisions':len(s.exec(select(Finding).where(Finding.kind=='decision',Finding.state=='accepted')).all()),
        }
        run=enqueue(s,'owner-feedback-gate:'+str(uuid4()))
        before['run_id']=run.id
        save_private(path,json.dumps(before))
        print(json.dumps({'status':'queued','run_id':run.id,'disposition':fb.disposition}))
    else:
        before=json.loads(path.read_text())
        run=s.get(Run,before['run_id'])
        if run.state in ('queued','running'):
            print(json.dumps({'status':'pending','run_id':run.id,'stage':run.stage}))
            raise SystemExit(2)
        fb=s.get(Feedback,before['feedback_id']);q=s.get(Question,before['question_id'])
        vault=Vault(cfg);incoming=vault.capture(INBOX);vault.close()
        source=s.exec(select(Source).where(Source.path=='feedback:'+q.id)).one()
        version=s.exec(select(Version).where(Version.source_id==source.id,Version.hash==source.version)).one()
        vault_answer=answers_from(incoming.body).get(q.id)
        checks={
            'run_completed':run.state=='completed',
            'feedback_retained':fb.state=='complete' and version.state=='complete',
            'answer_preserved':digest(q.answer)==before['answer_sha256'] and q.disposition==before['disposition'],
            'question_revision_preserved':q.revision==before['question_revision'],
            'question_resolved':q.state=='resolved' if fb.disposition!='tentative' else q.state=='answered',
            'original_versions_unchanged':originals(s)==before['originals'],
            'human_notes_preserved':list(outside(incoming.body))==before['outside'],
            'inbox_answer_matches':bool(vault_answer and digest(vault_answer[1])==before['answer_sha256'] and vault_answer[2]==before['disposition'] and vault_answer[0]==q.revision),
            'publication_readback':s.get(Publication,1).body==incoming.body and s.get(Publication,1).state=='published',
            'feedback_changed_review':bool(s.get(Artifact,'review:'+digest(json.dumps([(x.id,x.version) for x in s.exec(select(Source).where(Source.approved==True).order_by(Source.path))])))),
            'schedule_still_disabled':not s.get(Schedule,1).enabled,
        }
        if fb.disposition=='confirmed':
            checks['confirmation_did_not_approve_decision']=len(s.exec(select(Finding).where(Finding.kind=='decision',Finding.state=='accepted')).all())==before['accepted_decisions']
        if version.state=='complete':
            memory=Memory(cfg)
            memory.verify(source,version)
            memory.close()
            checks['hindsight_document_verified']=True
        report={'gate':'real-owner-feedback','status':'passed' if all(checks.values()) else 'failed',
                'run_id':run.id,'disposition':fb.disposition,'checks':checks,'error':run.error}
        print(json.dumps(report))
        if not all(checks.values()):raise SystemExit(1)
