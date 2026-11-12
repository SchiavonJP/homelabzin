"""Owner controls and read-only catalogue endpoints, registered with existing auth."""
from contextlib import closing
from collections import Counter
import re
from typing import Literal
from fastapi import APIRouter,Depends,Query
from pydantic import BaseModel,ConfigDict,Field
from sqlmodel import Session,select

from app import library_config,references
from app.models import Artifact,Run,AutomationPolicy,SourceConnection,ReferenceItem,now
from app.vault import DomainError,Vault
from app.karakeep import Karakeep


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')

class SaveConfig(Input):
    config:library_config.LibraryConfig
    expected_revision:int=Field(ge=0)

class Revision(Input):
    expected_revision:int=Field(ge=0)

class Approval(Revision):
    hash:str=Field(pattern=r'^[a-f0-9]{64}$')

class Classification(Revision):
    tags:list[str]=Field(max_length=30)
    projects:list[str]=Field(max_length=30)
    reading_status:Literal['unspecified','to-read','read','reference']|None=None

class RelationReview(Revision):
    state:Literal['accepted','rejected']

class SilverConfig(Input):
    folders:list[str]=Field(max_length=100)
    exclusions:list[str]=Field(max_length=100)

class AffineConfig(Input):
    workspace:str=Field(max_length=128)
    exclusions:list[str]=Field(max_length=10000)

class ConfigFile(Input):
    schema_version:Literal[1]
    library:library_config.LibraryConfig
    silverbullet:SilverConfig
    affine:AffineConfig|None=None

class ImportConfig(Input):
    document:ConfigFile
    expected_revision:int=Field(ge=0)
    expected_automation_revision:int=Field(ge=0)
    expected_affine_revision:int=Field(ge=0)


def validated(document,settings):
    from app.automation import normalized
    value=document.model_dump();value['silverbullet']['folders'],value['silverbullet']['exclusions']=normalized(**value['silverbullet'])
    a=value['affine']
    if a and (a['workspace'] not in settings.affine_workspaces or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',x) for x in a['exclusions'])):
        raise DomainError('invalid_affine_scope',422)
    cfg=document.library
    if any(x not in cfg.topics for x in cfg.aliases.values()):raise DomainError('topic_alias_target_invalid',422)
    return value


def router(engine,settings,actor,owner):
    r=APIRouter(prefix='/api/v1/xereta')

    class MigrationPreview(Input):
        migration_id:str|None=Field(default=None,max_length=36)
    class MigrationDecision(Input):
        id:str=Field(pattern=r'^[a-f0-9]{64}$')
        target:Literal['reference','karakeep','keep']
        url:str=Field(default='',max_length=4096)
    class MigrationClassify(Revision):
        decisions:list[MigrationDecision]=Field(max_length=200)
    class MigrationApply(Revision):
        ids:list[str]=Field(min_length=1,max_length=5)

    @r.post('/library/migrations/preview',dependencies=[Depends(owner)])
    def migration_preview(body:MigrationPreview):
        from app import readitlater
        with Session(engine) as s,closing(Vault(settings)) as vault:return readitlater.preview(s,settings,vault,body.migration_id)

    @r.get('/library/migrations/{ident}',dependencies=[Depends(owner)])
    def migration_get(ident:str):
        from app import readitlater
        with Session(engine) as s:return readitlater.public_manifest(readitlater.load(s,ident).value)

    @r.put('/library/migrations/{ident}/classification',dependencies=[Depends(owner)])
    def migration_classify(ident:str,body:MigrationClassify):
        from app import readitlater
        with Session(engine) as s:return readitlater.classify(s,ident,[x.model_dump() for x in body.decisions],body.expected_revision)

    @r.post('/library/migrations/{ident}/apply',dependencies=[Depends(owner)])
    def migration_apply(ident:str,body:MigrationApply):
        from app import readitlater
        with Session(engine) as s,closing(Vault(settings)) as vault:return readitlater.apply(s,settings,vault,ident,body.ids,body.expected_revision)

    @r.get('/library/config',dependencies=[Depends(owner)])
    def config():
        with Session(engine) as s:
            from app.automation import policy
            affine=s.get(SourceConnection,'affine')
            return {'config':library_config.current(s).model_dump(),'revision':library_config.revision(s),
                    'runtime_enabled':settings.library_enabled,'model':settings.litellm_model,
                    'karakeep_configured':bool(settings.karakeep_token.get_secret_value()),
                    'public_karakeep_url':settings.public_karakeep_url,'article_domains':settings.article_domains,
                    'progress':dict(Counter(x.state for x in s.exec(select(ReferenceItem)))),
                    'health':{key:s.get(Artifact,'connection-health:'+key).value for key in ('library-silverbullet','library-karakeep','library-publication') if s.get(Artifact,'connection-health:'+key)},
                    'last_sync':s.get(Artifact,'library-tick').value if s.get(Artifact,'library-tick') else {},
                    'automation_revision':policy(s).revision,'affine_revision':affine.revision if affine else 0}

    @r.put('/library/config',dependencies=[Depends(owner)])
    def save(body:SaveConfig):
        if body.config.karakeep_ready_list:
            with closing(Karakeep(settings)) as keep:keep.require_manual(body.config.karakeep_ready_list)
        with Session(engine) as s:return library_config.save(s,body.config.model_dump(),body.expected_revision)

    @r.get('/connections/export',dependencies=[Depends(owner)])
    def export():
        with Session(engine) as s:
            value=library_config.export_configuration(s)
            if value['affine']:
                value['affine']={k:value['affine'][k] for k in ('workspace','exclusions')}
            return value

    @r.post('/connections/import/preview',dependencies=[Depends(owner)])
    def preview_import(body:ConfigFile):
        return {'document':validated(body,settings),'activation':'all_changed_ingestion_scopes_paused','secrets_included':False}

    @r.post('/connections/import',dependencies=[Depends(owner)])
    def apply_import(body:ImportConfig):
        from app.automation import lock,policy
        value=validated(body.document,settings)
        with Session(engine) as s:
            lock(s);p=policy(s);a=s.get(SourceConnection,'affine')
            if library_config.revision(s)!=body.expected_revision or p.revision!=body.expected_automation_revision or (a.revision if a else 0)!=body.expected_affine_revision:
                raise DomainError('configuration_revision_conflict')
            if s.exec(select(Run).where(Run.state.in_(['queued','running']))).first():raise DomainError('connection_run_active')
            cfg=library_config.LibraryConfig(**value['library']);cfg.ingestion_paused=True;cfg.organization_paused=True
            row=s.get(Artifact,library_config.KEY) or Artifact(key=library_config.KEY)
            row.value={'config':cfg.model_dump(),'revision':body.expected_revision+1,'updated_at':now()};s.add(row)
            p.folders=value['silverbullet']['folders'];p.exclusions=value['silverbullet']['exclusions'];p.paused=True;p.revision+=1;s.add(p)
            if value['affine']:
                a=a or SourceConnection(id='affine');a.workspace=value['affine']['workspace'];a.exclusions=value['affine']['exclusions'];a.paused=True;a.revision+=1;a.approved_at=now();s.add(a)
            s.commit();return {'imported':True,'paused':True,'revision':library_config.revision(s)}

    @r.post('/library/sync',dependencies=[Depends(owner)],status_code=202)
    def sync():
        # Queue the existing serialized worker, never run a crawler in the HTTP handler.
        with Session(engine) as s:
            a=s.get(Artifact,'library-tick') or Artifact(key='library-tick');a.value={'next_at':''};s.add(a);s.commit()
        return {'queued':True}

    @r.get('/library/karakeep/lists',dependencies=[Depends(owner)])
    def lists():
        with closing(Karakeep(settings)) as keep:
            return {'lists':[{k:x.get(k) for k in ('id','name','type','public')} for x in keep.lists()]}

    @r.post('/library/karakeep/check',dependencies=[Depends(owner)])
    def check():
        with closing(Karakeep(settings)) as keep:rows=keep.lists()
        return {'healthy':True,'lists':len(rows)}

    @r.get('/references',dependencies=[Depends(actor)])
    def catalogue(q:str=Query(default='',max_length=500),topic:str=Query(default='',max_length=80),
                  state:str=Query(default='',max_length=40),offset:int=Query(default=0,ge=0),limit:int=Query(default=30,ge=1,le=100)):
        with Session(engine) as s:return references.list_items(s,q,topic,state,offset,limit)

    @r.get('/references/{ident}',dependencies=[Depends(actor)])
    def detail(ident:str):
        with Session(engine) as s:return references.details(s,ident)

    @r.post('/references/{ident}/promote',dependencies=[Depends(owner)])
    def promote(ident:str,body:Revision):
        with Session(engine) as s,closing(Vault(settings)) as vault:return references.promote(s,settings,vault,ident,body.expected_revision)

    @r.post('/references/{ident}/prepare',dependencies=[Depends(owner)])
    def prepare(ident:str,body:Revision):
        with Session(engine) as s:return references.prepare(s,settings,ident,body.expected_revision)

    @r.get('/references/{ident}/candidate',dependencies=[Depends(owner)])
    def candidate(ident:str):
        from app.models import ReferenceCapture
        with Session(engine) as s:
            item=references.item_of(s,ident)
            cap=s.exec(select(ReferenceCapture).where(ReferenceCapture.reference_id==ident,ReferenceCapture.hash==item.candidate_hash)).first()
            if not cap:raise DomainError('reference_capture_missing',404)
            return {'capture':cap.model_dump(),'item':references.dto(item)}

    @r.post('/references/{ident}/approve',dependencies=[Depends(owner)])
    def approve(ident:str,body:Approval):
        with Session(engine) as s:return references.approve(s,settings,ident,body.hash,body.expected_revision)

    @r.post('/references/{ident}/revoke',dependencies=[Depends(owner)])
    def revoke(ident:str,body:Revision):
        with Session(engine) as s:return references.revoke(s,ident,body.expected_revision)

    @r.put('/references/{ident}/classification',dependencies=[Depends(owner)])
    def classification(ident:str,body:Classification):
        with Session(engine) as s:return references.save_tags(s,ident,body.tags,body.projects,body.expected_revision,body.reading_status)

    @r.get('/relations',dependencies=[Depends(actor)])
    def relations(reference_id:str=Query(default='',max_length=128)):
        with Session(engine) as s:return {'relations':references.relations(s,reference_id)}

    @r.patch('/relations/{ident}',dependencies=[Depends(owner)])
    def review_relation(ident:str,body:RelationReview):
        with Session(engine) as s:return references.review_relation(s,ident,body.state,body.expected_revision)

    return r
