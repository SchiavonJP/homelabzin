"""One operational configuration, validated equally for the UI and JSON import."""
import json
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlmodel import select

from app.models import Artifact, ReferenceItem, Run, now
from app.vault import DomainError, source_path

KEY='library-config:v1'


class LibraryConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reference_folders:list[str]=Field(default_factory=lambda:['space/Referências/'],max_length=50)
    journal_folders:list[str]=Field(default_factory=list,max_length=50)
    legacy_folders:list[str]=Field(default_factory=lambda:['space/ReadItLater Inbox/'],max_length=50)
    excluded_affine:list[str]=Field(default_factory=list,max_length=10000)
    reference_exclusions:list[str]=Field(default_factory=list,max_length=100)
    topics:list[str]=Field(default_factory=lambda:['AI','Development','Homelab','Research','Productivity'],max_length=100)
    aliases:dict[str,str]=Field(default_factory=dict,max_length=100)
    concepts:dict[str,str]=Field(default_factory=dict,max_length=100)
    organization_paused:bool=True
    ingestion_paused:bool=True
    organization_per_day:int=Field(default=50,ge=1,le=50)
    organization_minutes:int=Field(default=5,ge=1,le=5)
    karakeep_ready_list:str=Field(default='',max_length=128,pattern=r'^[a-zA-Z0-9_-]*$')
    karakeep_inbox_list:str=Field(default='',max_length=128,pattern=r'^[a-zA-Z0-9_-]*$')

    @model_validator(mode='after')
    def separate_lists(self):
        if self.karakeep_ready_list and self.karakeep_ready_list==self.karakeep_inbox_list:
            raise ValueError('reading_inbox_cannot_be_ready_list')
        return self

    @field_validator('reference_folders','journal_folders','legacy_folders')
    @classmethod
    def folders(cls,values):
        for v in values:
            if not v.endswith('/') or len(v)>1000:raise ValueError('folder_required')
            source_path(v+'scope-check.md')
            if any(x.casefold()=='_agentknowledge' for x in v.split('/')):raise ValueError('managed_scope_forbidden')
        return sorted(set(values))

    @field_validator('topics')
    @classmethod
    def topic_names(cls,values):
        if any(not x.strip() or len(x)>80 or any(c in x for c in '\n\r[]#|') for x in values):raise ValueError('invalid_topic')
        return list(dict.fromkeys(x.strip() for x in values))

    @field_validator('concepts')
    @classmethod
    def concept_values(cls,values):
        if any(not k.strip() or len(k)>100 or len(v)>4000 or '\n' in k for k,v in values.items()):raise ValueError('invalid_concept')
        return values

    @field_validator('reference_exclusions')
    @classmethod
    def exclude_paths(cls,values):
        for x in values:source_path(x if not x.endswith('/') else x+'scope-check.md')
        return values


def current(s):
    a=s.get(Artifact,KEY)
    return LibraryConfig(**a.value['config']) if a else LibraryConfig()


def revision(s):
    a=s.get(Artifact,KEY)
    return a.value['revision'] if a else 0


def save(s,data,expected_revision):
    from app.automation import lock
    cfg=LibraryConfig(**data);lock(s)
    if revision(s)!=expected_revision:raise DomainError('library_revision_conflict')
    if s.exec(select(Run).where(Run.state.in_(['queued','running']))).first():raise DomainError('connection_run_active')
    if any(target not in cfg.topics for target in cfg.aliases.values()):raise DomainError('topic_alias_target_invalid',422)
    old=current(s)
    # Changing scope cannot carry a previous activation into the new scope.
    scope=('reference_folders','journal_folders','legacy_folders','excluded_affine','reference_exclusions','karakeep_ready_list')
    if any(getattr(old,k)!=getattr(cfg,k) for k in scope):cfg.ingestion_paused=True
    a=s.get(Artifact,KEY) or Artifact(key=KEY)
    a.value={'revision':expected_revision+1,'config':cfg.model_dump(),'updated_at':now()}
    s.add(a);s.commit()
    return {'revision':revision(s),'config':cfg.model_dump()}


def catalogue_only(path,config):
    if path in config.get('excluded_affine',[]):return True
    return any(path.startswith(x) for x in config.get('reference_folders',[])+config.get('legacy_folders',[]))


def scope(s):
    cfg=current(s)
    paths=['reference:'+x.id for x in s.exec(select(ReferenceItem).where(ReferenceItem.approved_hash!=''))]
    return {'approved_at':s.get(Artifact,KEY).value.get('updated_at','') if s.get(Artifact,KEY) else '',
            'paused':cfg.ingestion_paused,'ready_paths':paths,'catalogue':cfg.model_dump()}


def export_configuration(s):
    from app.automation import policy
    from app.connections import scopes
    p=policy(s)
    return {'schema_version':1,'library':current(s).model_dump(),
            'silverbullet':{'folders':p.folders,'exclusions':p.exclusions},
            'affine':scopes(s).get('affine')}
