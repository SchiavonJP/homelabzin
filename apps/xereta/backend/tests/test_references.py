import json
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from sqlmodel import Session,select

from test_xereta import settings,client,owner
from app import references,library_config,automation,readitlater
from app.article_reader import public_url,public_addresses,ArticleText,fetch_article
from app.connections import Readers
from app.models import Artifact,ReferenceItem,ReferenceCapture,KnowledgeRelation,Source,Version,Run
from app.vault import DomainError,Capture,digest


class Notes:
    def __init__(self,files=None):self.files=files or {};self.writes=[]
    def inventory(self):return [{'path':p,'size':len(b),'lastModified':digest(b)} for p,b in self.files.items()]
    def capture(self,path):
        if path not in self.files:raise DomainError('vault_file_missing',404)
        return Capture(path,self.files[path],digest(self.files[path]),'"sha256:'+digest(self.files[path])+'"')
    def create_reference(self,path,body):
        if path in self.files:raise DomainError('vault_revision_conflict')
        self.files[path]=body;self.writes.append(path);return self.capture(path)
    def write_library(self,path,body,etag=None):self.files[path]=body;self.writes.append(path);return self.capture(path)
    def permalink(self,path):return 'https://silverbullet.joaopaulo.me/'+path


def cfg(s,**values):
    data=library_config.current(s).model_dump();data.update(values)
    return library_config.save(s,data,library_config.revision(s))


def test_cataloguing_does_not_create_knowledge_or_capture(client,settings):
    with Session(client.app.state.engine) as s:
        assert references.extract(s,'space/Referências/Tool.md','# Tool\nCould help with chunking. https://github.com/example/tool\n#AI')==1
        references.extract(s,'space/Referências/Tool.md','# Tool\nCould help with chunking. https://github.com/example/tool\n#AI')
        assert len(s.exec(select(ReferenceItem)).all())==1
        assert len(s.exec(select(ReferenceCapture)).all())==0
        assert len(s.exec(select(Source)).all())==0
        assert len(s.exec(select(Version)).all())==0
        item=s.exec(select(ReferenceItem)).one()
        assert not item.approved_hash and item.state=='catalogued'
        assert references.list_items(s,'chunking')['total']==1


def test_literal_search_does_not_treat_percent_as_wildcard(client):
    with Session(client.app.state.engine) as s:
        references.item_url(s,'https://example.org/a','Normal');s.commit()
        assert references.list_items(s,'%')['total']==0


def test_metadata_prompt_excludes_snapshots_and_validates_topics(client,settings,monkeypatch):
    seen=[]
    def post(self,url,**kwargs):
        seen.append(kwargs['json']);return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"topics":["AI"]}'}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx.Client,'post',post)
    with Session(client.app.state.engine) as s:
        item=references.item_url(s,'https://example.org/a','Document ingestion',context='May help my project');s.commit()
        references.save_capture(s,item,{'title':'Article','body':'UNREAD ARTICLE SECRET '*100,'url':item.url})
        references.organize_one(s,settings,item,library_config.current(s))
        assert 'UNREAD ARTICLE SECRET' not in json.dumps(seen)
        assert seen[0]['model']=='generalist'
        assert item.suggested_tags==['AI'] and not item.approved_hash
        assert not s.exec(select(Source)).all()


def test_approval_is_specific_version_and_revoke_is_enforced(client,settings):
    settings.library_enabled=True
    with Session(client.app.state.engine) as s:
        cfg(s,ingestion_paused=False)
        item=references.item_url(s,'https://example.org/a','Article');s.commit()
        first=references.save_capture(s,item,{'body':'Original text '*30,'url':item.url})
        with pytest.raises(DomainError,match='reference_readiness_required'):references.capture(s,settings,'reference:'+item.id)
        references.approve(s,settings,item.id,first['capture']['hash'],first['item']['revision'])
        cap=references.capture(s,settings,'reference:'+item.id);assert cap.hash==first['capture']['hash']
        old=first['capture']['hash']
        references.save_capture(s,item,{'body':'Changed text '*30,'url':item.url})
        with pytest.raises(DomainError,match='reference_readiness_required'):references.capture(s,settings,'reference:'+item.id)
        with pytest.raises(DomainError,match='reference_capture_changed'):references.approve(s,settings,item.id,old,item.revision)
        assert len(s.exec(select(ReferenceCapture)).all())==2
        references.revoke(s,item.id,item.revision)
        assert not item.approved_hash


def test_reference_scope_wins_over_broad_knowledge_scope_and_manual_capture(client,settings):
    settings.library_enabled=True
    with Session(client.app.state.engine) as s:
        p=automation.policy(s);p.folders=['space/']
        assert not automation.in_scope('space/Referências/a.md',p)
        assert not automation.in_scope('space/ReadItLater Inbox/a.md',p)
        readers=Readers(Notes({'space/Referências/a.md':'Reference link'}),settings);readers.session=s
        try:
            with pytest.raises(DomainError,match='reference_catalogue_only'):readers.capture('space/Referências/a.md')
        finally:readers.close()


def test_owner_only_controls_reader_can_only_search(client,settings):
    h=owner(client,settings);reader={'Authorization':'Bearer '+settings.agent_read_token.get_secret_value()}
    for path in ['/library/config','/connections/export']:
        assert client.get('/api/v1/xereta'+path,headers=reader).status_code==403
    with Session(client.app.state.engine) as s:item=references.item_url(s,'https://example.org/a','Article');s.commit();ident=item.id
    assert client.get('/api/v1/xereta/references',headers=reader).status_code==200
    for action in ('prepare','approve','revoke'):
        assert client.post('/api/v1/xereta/references/'+ident+'/'+action,headers=reader,json={'expected_revision':0,'hash':'a'*64}).status_code==403
    data=client.get('/api/v1/xereta/library/config',headers=h).json()
    assert data['model']=='generalist' and 'karakeep_token' not in json.dumps(data)


def test_configuration_json_roundtrip_unknown_keys_and_stale_revision(client,settings):
    h=owner(client,settings)
    export=client.get('/api/v1/xereta/connections/export',headers=h).json()
    assert 'secret' not in json.dumps(export) and 'token' not in json.dumps(export)
    assert client.post('/api/v1/xereta/connections/import/preview',headers=h,json=export).status_code==200
    invalid={**export,'token':'should-never-import'}
    assert client.post('/api/v1/xereta/connections/import/preview',headers=h,json=invalid).status_code==422
    body={'document':export,'expected_revision':0,'expected_automation_revision':0,'expected_affine_revision':0}
    r=client.post('/api/v1/xereta/connections/import',headers=h,json=body)
    assert r.status_code==200,r.text
    assert client.post('/api/v1/xereta/connections/import',headers=h,json=body).status_code==409
    with Session(client.app.state.engine) as s:assert library_config.current(s).ingestion_paused


def test_rejected_suggestion_survives_rerun_and_native_indexes_preserve_owner_edits(client):
    notes=Notes()
    with Session(client.app.state.engine) as s:
        a=references.item_url(s,'https://example.org/a','A');b=references.item_url(s,'https://example.org/b','B');s.commit()
        a.tags=['AI'];s.add(a);references.relate(s,a.id,b.id,'Shared topic');s.commit()
        edge=s.exec(select(KnowledgeRelation)).one();references.review_relation(s,edge.id,'rejected',0)
        assert references.relate(s,a.id,b.id,'Shared topic').state=='rejected'
        references.publish_indexes(s,notes,library_config.current(s))
        index='space/_AgentKnowledge/Referências/index.md'
        assert '](<' in notes.files[index] and 'tags:' in notes.files['space/_AgentKnowledge/Referências/'+a.id+'.md']
        notes.files[index]+='\nOwner annotation'
        a.title='Changed';s.add(a);s.commit()
        # Force changed index labels; original owner annotation must survive.
        with pytest.raises(DomainError,match='library_publication_conflict'):references.publish_indexes(s,notes,library_config.current(s))
        assert 'Owner annotation' in notes.files[index]


def test_parser_drops_scripts_and_unsafe_destinations(monkeypatch):
    parser=ArticleText();parser.feed('<html><script>SECRET</script><nav>Menu</nav><article><p>Article text</p></article></html>')
    assert parser.text()=='Article text'
    for bad in ['file:///etc/passwd','https://user:pass@example.org/a','https://example.org:4000/a','https://example.org/\\escape']:
        with pytest.raises(DomainError):public_url(bad)
    monkeypatch.setattr('socket.getaddrinfo',lambda *args,**kwargs:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(DomainError,match='article_private_destination'):public_addresses('example.org',443)
    with pytest.raises(DomainError,match='article_domain_not_approved'):fetch_article('https://example.org/a',[])


def test_readitlater_preview_and_reference_migration_are_idempotent(client,settings):
    path='space/ReadItLater Inbox/Tool.md';body='---\nsource: https://github.com/example/tool\n---\n# Tool\nFull clipped original body is retained, never classified by AI.'
    notes=Notes({path:body})
    with Session(client.app.state.engine) as s:
        preview=readitlater.preview(s,settings,notes)
        row=preview['rows'][0]
        assert preview['complete'] and row['target']=='reference'
        assert not s.exec(select(ReferenceItem)).all()
        with pytest.raises(DomainError,match='migration_classification_required'):readitlater.apply(s,settings,notes,preview['id'],[row['id']],preview['revision'])
        saved=readitlater.classify(s,preview['id'],[{'id':row['id'],'target':'reference','url':row['url']}],preview['revision'])
        result=readitlater.apply(s,settings,notes,preview['id'],[row['id']],saved['revision'])
        assert notes.files[path]==body and len(notes.writes)==1
        readitlater.apply(s,settings,notes,preview['id'],[row['id']],result['revision'])
        assert len(notes.writes)==1 and len(s.exec(select(ReferenceItem)).all())==1
        assert not s.exec(select(Source)).all()
        assert not s.exec(select(ReferenceCapture)).all()
        assert not s.exec(select(ReferenceItem)).one().approved_hash
        archives=list((settings.state_path/'readitlater').rglob('*.md'));assert len(archives)==1 and archives[0].read_text()==body


def test_failed_configuration_import_is_atomic(client,settings):
    h=owner(client,settings)
    with Session(client.app.state.engine) as s:
        before=library_config.revision(s);cfg(s)
    data=client.get('/api/v1/xereta/connections/export',headers=h).json()
    r=client.post('/api/v1/xereta/connections/import',headers=h,json={'document':data,'expected_revision':0,'expected_automation_revision':0,'expected_affine_revision':0})
    assert r.status_code==409
    with Session(client.app.state.engine) as s:assert library_config.revision(s)==before+1


def test_only_approved_reference_enters_shared_worker_and_rerun_is_idempotent(client,settings,monkeypatch):
    from test_automation import adapters,activate
    from app.automatic_worker import execute
    from app.models import DailyUsage
    from app import automatic_worker
    from test_automation import VaultFake,MemoryFake
    from app.memory import validate_review
    settings.library_enabled=True
    vault=VaultFake();vault.settings=settings
    vault.files={'space/Referências/Unread.md':'# Unread\nhttps://example.org/unread'}
    memory=MemoryFake()
    monkeypatch.setattr(automatic_worker,'Vault',lambda cfg:vault)
    monkeypatch.setattr(automatic_worker,'Memory',lambda cfg:memory)
    monkeypatch.setattr(automatic_worker,'draft',lambda cfg,sources,versions,trusted:validate_review({'items':[]},sources,versions,trusted))
    with Session(client.app.state.engine) as s:
        cfg(s,ingestion_paused=False)
        unread=references.item_url(s,'https://example.org/unread','Unread');ready=references.item_url(s,'https://example.org/read','Read');s.commit()
        cap=references.save_capture(s,ready,{'body':'A reviewed document with an explicit claim. '*12,'url':ready.url})
        references.approve(s,settings,ready.id,cap['capture']['hash'],cap['item']['revision'])
        read_id=ready.id
        rid=activate(s,settings,notes=2,folders=['space/'])
    execute(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        job=s.get(Run,rid);assert job.state=='completed',job.error
        sources=s.exec(select(Source)).all();assert len(sources)==1 and sources[0].path=='reference:'+read_id
        first=len(memory.posts)
        from app.services import enqueue
        next_id=enqueue(s,'reference-idempotency').id
    execute(client.app.state.engine,settings,next_id)
    assert len(memory.posts)==first


def test_rejected_topic_is_not_resurrected(client,settings,monkeypatch):
    def post(self,url,**kwargs):return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"topics":["AI"]}'}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx.Client,'post',post)
    with Session(client.app.state.engine) as s:
        item=references.item_url(s,'https://example.org/a','AI');s.commit()
        references.organize_one(s,settings,item,library_config.current(s))
        references.save_tags(s,item.id,[],[],item.revision)
        item.description='New metadata';s.add(item);s.commit()
        references.organize_one(s,settings,item,library_config.current(s))
        assert 'AI' not in item.suggested_tags


def test_karakeep_enumeration_never_requests_article_content(settings):
    from app.karakeep import Karakeep
    calls=[]
    def handle(request):
        calls.append(str(request.url));return httpx.Response(200,json={'bookmarks':[],'nextCursor':None})
    with closing(Karakeep(settings,httpx.MockTransport(handle))) as keep:keep.page()
    assert 'includeContent=false' in calls[0]
    assert '/api/v1/bookmarks' in calls[0]


def test_relative_internal_links_survive_both_vault_roots():
    import posixpath
    source='space/_AgentKnowledge/Referências/test.md';target='space/Referências/Ferramenta.md'
    link=references.wiki(target,'Ferramenta',source)
    relative=link.split('](<',1)[1].removesuffix('>)')
    assert posixpath.normpath(posixpath.join(posixpath.dirname(source),relative))==target
    assert posixpath.normpath(posixpath.join(posixpath.dirname(source.removeprefix('space/')),relative))==target.removeprefix('space/')


def test_external_reference_never_establishes_owner_decision():
    from app.memory import validate_review
    source=SimpleNamespace(id='ref',path='reference:00000000-0000-4000-8000-000000000000')
    version=SimpleNamespace(hash='v',body='An article author decided to install a tool.')
    item={'issue':'install','kind':'decision','text':'Owner installed the tool','reason':'Wrong authority','evidence':[{'source_id':'ref','quote':'decided to install a tool'}]}
    with pytest.raises(DomainError,match='external_reference_cannot_establish_owner_decision'):
        validate_review({'items':[item]},[source],{'ref':version},{'ref'})


def test_title_only_update_does_not_create_digest_work(client,settings):
    with Session(client.app.state.engine) as s:
        item=references.item_url(s,'https://example.org/a','Article');s.commit()
        first=references.save_capture(s,item,{'title':'Original title','body':'Original article body '*20,'url':item.url})
        references.approve(s,settings,item.id,first['capture']['hash'],first['item']['revision'])
        second=references.save_capture(s,item,{'title':'Updated display title','body':'Original article body '*20,'url':item.url})
        assert first['capture']['hash']==second['capture']['hash']
        assert item.approved_hash==item.candidate_hash
        assert len(s.exec(select(ReferenceCapture)).all())==1


def test_reference_urls_encode_markup_and_unicode_without_dropping_query_values():
    value=public_url('https://example.org/café/<script>?q=ação&token=keep-this-value')
    assert '<' not in value and '>' not in value
    assert '/caf%C3%A9/%3Cscript%3E' in value and 'token=keep-this-value' in value


def test_marking_read_never_authorizes_digest(client):
    with Session(client.app.state.engine) as s:
        item=references.item_url(s,'https://example.org/a','Article');s.commit()
        references.save_tags(s,item.id,[],[],item.revision,'read')
        assert references.dto(item)['reading_status']=='read'
        assert item.state=='catalogued' and not item.approved_hash
        assert not s.exec(select(ReferenceCapture)).all() and not s.exec(select(Source)).all()


def test_legacy_linked_heading_selects_original_not_article_citations(client):
    body='[[ReadItLater]] [[Article]]\n\n# [Original article](https://example.org/article)\n\nA citation https://other.example.org/cited and another https://third.example.org/.'
    assert references.primary_link(body)==('https://example.org/article','Original article')
    with Session(client.app.state.engine) as s:
        assert references.catalogue_copy(s,'affine:main:workspace:copy',body)
        assert not s.exec(select(Source)).all()


def test_journal_mention_is_not_mistaken_for_a_clipped_article(client):
    with Session(client.app.state.engine) as s:
        references.item_url(s,'https://example.org/tool','Tool');s.commit()
        assert not references.catalogue_copy(s,'space/Diário/Today.md','# Today\nI might use this tool later: https://example.org/tool')


def test_verified_legacy_article_copy_is_not_independent_evidence(client,settings):
    from app.connections import relate,family
    with Session(client.app.state.engine) as s:
        item=references.item_url(s,'https://example.org/article','Article');s.commit()
        body='[[ReadItLater]]\n# [Article](https://example.org/article)\nOriginal clipped content.'
        old=Source(path='affine:main:workspace:copy',title='Imported',provider='affine',version=digest(body),approved=True)
        s.add(old);s.commit();s.refresh(old)
        old.family_id=old.id;s.add(old)
        s.add(Version(source_id=old.id,hash=old.version,body=body,title=old.title,etag='x'));s.commit()
        fresh=Source(path='reference:'+item.id,title='Article',provider='references',approved=True)
        s.add(fresh);s.commit();s.refresh(fresh)
        relate(s,fresh,'A newly captured plain-text version.',settings);s.commit()
        assert family(fresh)==old.id and old.approved


def test_karakeep_sync_cannot_undo_explicit_owner_revocation(client,settings,monkeypatch):
    import time
    from pydantic import SecretStr
    settings.karakeep_token=SecretStr('synthetic-test-token');settings.library_enabled=True
    class Keep:
        identifier=staticmethod(lambda value:value)
        def __init__(self,*args):pass
        def close(self):pass
        def page(self,cursor=None,list_id=None):return [{'id':'bookmark','title':'Article','content':{'type':'link','url':'https://example.org/a'}}],None
        def require_manual(self,list_id):pass
        def is_ready(self,*args):return True
        def capture(self,ident):return {'title':'Article','body':'Reviewed article text. '*30,'url':'https://example.org/a'}
    monkeypatch.setattr(references,'Karakeep',Keep)
    with Session(client.app.state.engine) as s:
        cfg(s,karakeep_ready_list='ready');cfg(s,ingestion_paused=False)
        policy=library_config.current(s)
        references.sync_karakeep(s,settings,policy,time.monotonic()+100)
        item=s.exec(select(ReferenceItem)).one();assert item.approved_hash
        references.revoke(s,item.id,item.revision)
        references.sync_karakeep(s,settings,policy,time.monotonic()+100)
        s.refresh(item);assert not item.approved_hash
        references.approve(s,settings,item.id,item.candidate_hash,item.revision)
        assert item.approved_hash
