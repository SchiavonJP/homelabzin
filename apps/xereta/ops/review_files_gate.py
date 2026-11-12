"""Live, read-only qualification for the per-item review migration.

Optionally supply --baseline with a private, pre-migration hash manifest.
No answers or note bodies are printed.
"""
import argparse
import json
from pathlib import Path

from sqlmodel import Session,select
from sqlalchemy import text
from app.config import Settings
from app.db import make_engine
from app.models import Question, Finding, Feedback, Source, ReviewPage, Publication, Schedule
from app.review import question_path, answer
from app.vault import Vault,INBOX,REVIEW_INDEX,digest,eligible

parser=argparse.ArgumentParser()
parser.add_argument('--baseline')
args=parser.parse_args()
cfg=Settings();vault=Vault(cfg)
with Session(make_engine(cfg.database_url)) as s:
    questions=list(s.exec(select(Question).where(Question.state!='withdrawn')))
    findings=list(s.exec(select(Finding)))
    pages=list(s.exec(select(ReviewPage)))
    source_heads={x.id:x.version for x in s.exec(select(Source))}
    checks={
        'one_page_per_item':len(pages)==len(questions)+len(findings)+1,
        'unique_question_paths':len({question_path(q) for q in questions})==len(questions),
        'all_pages_published':bool(pages) and all(p.state=='published' and not p.error for p in pages),
        'all_pages_readback':all(vault.capture(p.path).body==p.body for p in pages),
        'question_answers_match':all(answer(vault.capture(question_path(q)).body)==q.answer for q in questions),
        'no_visible_template_comments':all('<!-- xereta:' not in p.body for p in pages),
        'index_is_links_only':'## Resposta' not in vault.capture(REVIEW_INDEX).body,
        'review_excluded_from_evidence':not any(eligible(p.path) for p in pages),
        'publication_complete':s.get(Publication,1).state=='published',
        'schedule_disabled':not s.get(Schedule,1).enabled,
        'schema_migrated':s.execute(text('select version_num from alembic_version')).scalar()=='0002',
    }
    if args.baseline:
        old=json.loads(Path(args.baseline).read_text())
        checks.update({
            'answers_and_revisions_preserved':{q.id:{'revision':q.revision,'state':q.state,'answer':digest(q.answer)} for q in questions}==old['questions'],
            'feedback_records_preserved':sorted(f.id for f in s.exec(select(Feedback)))==old['feedback'],
            'source_versions_preserved':source_heads==old['sources'],
            'findings_preserved':sorted(f.id for f in findings)==old['findings'],
            'legacy_file_preserved':vault.capture(INBOX).hash==old['legacy_sha256'],
            'legacy_private_backup_verified':digest((cfg.state_path/'legacy-review'/(old['legacy_sha256']+'.md')).read_text())==old['legacy_sha256'],
        })
    print(json.dumps({'gate':'per-item-review-files','passed':all(checks.values()),'checks':checks,
                      'counts':{'questions':len(questions),'findings':len(findings),'pages':len(pages)}}))
    if not all(checks.values()):raise SystemExit(1)
