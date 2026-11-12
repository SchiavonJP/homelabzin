"""Safe status summary, without note bodies or credentials. Run inside app."""
import json
from sqlmodel import Session,select
from app.config import Settings
from app.db import make_engine
from app.models import Source,Version,Run,Question,Finding,Feedback,Publication,Schedule,Artifact
cfg=Settings();engine=make_engine(cfg.database_url)
with Session(engine) as s:
    print(json.dumps({
      'sources':[{'id':x.id,'state':x.state,'version':x.version,'error':x.error} for x in s.exec(select(Source))],
      'versions':[{'source_id':x.source_id,'hash':x.hash,'state':x.state,'operation_id':x.operation_id} for x in s.exec(select(Version))],
      'runs':[{'id':x.id,'state':x.state,'stage':x.stage,'error':x.error,'result':x.result} for x in s.exec(select(Run).order_by(Run.created_at.desc()).limit(3))],
      'questions':len(s.exec(select(Question)).all()),'findings':len(s.exec(select(Finding)).all()),
      'feedback':len(s.exec(select(Feedback)).all()),'publication':s.get(Publication,1).state,
      'schedule_enabled':s.get(Schedule,1).enabled,
      'artifacts':[x.key for x in s.exec(select(Artifact))]
    },indent=2))
