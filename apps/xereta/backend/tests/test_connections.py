import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from sqlmodel import Session, select

from test_xereta import client, settings, owner
from test_automation import adapters, activate, VaultFake, MemoryFake
from app import automation as auto, connections, automatic_worker
from app.automatic_worker import reuse_extraction, views
from app.connections import AffineReader, Readers, affine_path, family
from app.models import (Artifact, AutomationRun, IntakeNote, IntakeSection, Question, Run, Source,
                        SourceConnection, SourceRelationship, Version)
from app.services import execute_run
from app.vault import DomainError, digest


@pytest.fixture
def affine(monkeypatch, settings):
    settings.affine_workspaces=['workspace']
    settings.affine_reader_token=SecretStr('test-reader-key-not-a-real-credential')
    state={'calls':[], 'failure':False, 'files':{'doc-a':('AFFiNE A','A separate AFFiNE statement.'),'doc-b':('AFFiNE B','Another AFFiNE statement.')}}
    def handle(req):
        state['calls'].append((req.url.path,json.loads(req.content)))
        if state['failure']:
            return httpx.Response(403,json={'secret':'never expose this provider body'})
        body=json.loads(req.content)
        if req.url.path=='/status':return httpx.Response(200,json={'state':'healthy'})
        if req.url.path=='/inventory':
            return httpx.Response(200,json={'items':[{'id':key,'title':title,'updated_at':'v1'} for key,(title,text) in state['files'].items()], 'complete':True,'cursor':None})
        if req.url.path=='/capture':
            title,text=state['files'][body['document']];raw=state.get('snapshot',b'synthetic-snapshot')
            return httpx.Response(200,json={'complete':True,'title':title,'body':text,'snapshot':base64.b64encode(raw).decode(),
                'snapshot_sha256':digest(raw),'markdown_sha256':digest(text),'warnings':[]})
        raise AssertionError(req.url.path)
    klass=AffineReader
    monkeypatch.setattr(connections,'AffineReader',lambda cfg:klass(cfg,httpx.MockTransport(handle)))
    return state


def approve(s,paused=False,exclusions=None):
    c=SourceConnection(id='affine',workspace='workspace',exclusions=exclusions or [],approved_at='2026-11-08T00:00:00+00:00',paused=paused)
    s.add(c);s.commit()


def test_connection_controls_owner_only_and_no_secret_dto(client,settings,affine):
    reader={'Authorization':'Bearer '+settings.agent_read_token.get_secret_value()}
    for path,method,body in [('/connections','get',None),('/connections/affine/preview','post',{'workspace':'workspace','exclusions':[],'expected_revision':0}),
                             ('/connections/affine/pause','post',{'expected_revision':0})]:
        r=getattr(client,method)('/api/v1/xereta'+path,headers=reader,**({'json':body} if body is not None else {}))
        assert r.status_code==403
    h=owner(client,settings)
    r=client.get('/api/v1/xereta/connections',headers=h)
    assert r.status_code==200 and 'test-reader-key' not in r.text
    preview=client.post('/api/v1/xereta/connections/affine/preview',headers=h,json={'workspace':'workspace','exclusions':[],'expected_revision':0})
    assert preview.status_code==200 and preview.json()['included']==2
    assert all(path=='/inventory' for path,_ in affine['calls'])
    saved=client.put('/api/v1/xereta/connections/affine/scope',headers=h,json={'workspace':'workspace','exclusions':['doc-b'],'expected_revision':0})
    assert saved.status_code==200 and saved.json()['paused']
    with Session(client.app.state.engine) as s:assert not s.exec(select(Run)).all()
    assert client.put('/api/v1/xereta/connections/affine/scope',headers=h,json={'workspace':'workspace','exclusions':[],'expected_revision':0}).status_code==409
    assert client.post('/api/v1/xereta/connections/affine/resume',headers=h,json={'expected_revision':1}).status_code==200


def test_identity_rejects_urls_and_path_traversal():
    for value in ('https://evil.invalid','affine:main:../escape:doc','affine:main:workspace:doc?token=x'):
        assert not connections.source_eligible(value)
    assert affine_path('workspace','doc')=='affine:main:workspace:doc'


def test_mixed_worker_shared_quota_and_provider_fairness(client,settings,adapters,affine):
    vault,memory=adapters
    with Session(client.app.state.engine) as s:
        approve(s)
        rid=activate(s,settings,notes=4)
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        job=s.get(Run,rid)
        assert job.state=='completed',job.error
        sources=s.exec(select(Source).where(Source.provider!='feedback')).all()
        assert len(sources)==4 and {x.provider for x in sources}=={'silverbullet','affine'}
        assert auto.summary(s,True)['budget']['notes_used']==4
        assert len(s.exec(select(Question).where(Question.state=='open')).all())<=3
        assert all(any((settings.state_path/'captures'/x.id).glob('*.bin')) for x in sources if x.provider=='affine')
        assert all(x.state=='processed' for x in s.exec(select(IntakeNote)) if x.source_id)
        before=len(memory.posts)
        rid2=connections.control(s,0,True)
        assert rid2['paused']
        assert auto.policy(s).paused is False
    assert before>0


def test_affine_auth_outage_does_not_block_silverbullet_or_mark_missing(client,settings,adapters,affine):
    affine['failure']=True
    with Session(client.app.state.engine) as s:
        approve(s)
        note=IntakeNote(path=affine_path('workspace','old'),state='processed',version='old-version')
        s.add(note);s.commit();rid=activate(s,settings,notes=2)
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).state=='completed'
        assert s.get(IntakeNote,affine_path('workspace','old')).state=='processed'
        assert s.get(Artifact,'connection-health:affine').value['state']=='reauth_required'
        assert len(s.exec(select(Source)).all())==2


def test_silverbullet_outage_does_not_block_affine(client,settings,adapters,affine):
    vault,memory=adapters
    vault.inventory=lambda:(_ for _ in ()).throw(DomainError('silverbullet_unavailable',503))
    with Session(client.app.state.engine) as s:approve(s);rid=activate(s,settings,notes=2)
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        job=s.get(Run,rid);assert job.state=='completed',job.error
        assert {x.provider for x in s.exec(select(Source))}=={'affine'}


def test_configured_but_unapproved_affine_never_read_by_worker(client,settings,adapters,affine):
    with Session(client.app.state.engine) as s:rid=activate(s,settings,notes=1)
    execute_run(client.app.state.engine,settings,rid)
    assert not affine['calls']


def test_affine_rename_changes_version_not_source_identity(settings,affine):
    reader=connections.AffineReader(settings)
    try:
        first=reader.capture(affine_path('workspace','doc-a'))
        affine['files']['doc-a']=('Renamed',affine['files']['doc-a'][1])
        second=reader.capture(first.path)
        assert first.path==second.path and first.hash!=second.hash and first.body==second.body
    finally:reader.close()


def test_capture_failure_does_not_return_private_provider_body(settings,affine):
    affine['failure']=True
    reader=connections.AffineReader(settings)
    try:
        with pytest.raises(DomainError,match='affine_reauth_required') as e:reader.capture(affine_path('workspace','doc-a'))
        assert 'never expose' not in str(e.value)
    finally:reader.close()


def test_exact_copy_reuses_verified_sections_and_divergence_keeps_versions(client,settings):
    with Session(client.app.state.engine) as s:
        original=Source(path='space/Note.md',title='Note',state='complete',approved=True)
        original.family_id=original.id;original.version=digest('Same text.');s.add(original)
        old=Version(source_id=original.id,hash=original.version,body='Same text.',etag='',state='complete');s.add(old);s.commit()
        copy=Source(path=affine_path('workspace','doc'),title='Note',provider='affine',connection_id='affine',external_id='workspace/doc',approved=True)
        v=Version(source_id=copy.id,hash=digest('Note\n\0Same text.'),body='Same text.',etag='')
        s.add_all([copy,v]);connections.relate(s,copy,v.body,settings);copy.version=v.hash;s.add(copy);s.commit()
        assert family(copy)==family(original)
        original_units=auto.ensure_sections(s,original,old)
        for part in original_units:part.state='reviewed';s.add(part)
        s.commit()
        units=auto.ensure_sections(s,copy,v);reuse_extraction(s,copy,v,units);s.commit()
        assert all(u.reused_from and u.state=='retained' for u in units)
        proxies,versions,docs=views(s,units)
        assert proxies[0].provenance_version==old.hash and proxies[0].provenance_source_id==original.id
        assert versions[units[0].id].hash==v.hash
        changed=Version(source_id=copy.id,hash=digest('Different'),body='Different',etag='');s.add(changed);copy.version=changed.hash;s.add(copy);s.commit()
        relation=connections.relationships(s)[0]
        assert relation['diverged'] and relation['state']=='linked'
        assert s.get(Version,old.id).body=='Same text.'
        assert s.get(Source,original.id).version==old.hash


def test_title_only_suggests_and_owner_can_link_without_changing_approvals(client,settings):
    with Session(client.app.state.engine) as s:
        a=Source(path='space/Topic.md',title='Topic',approved=True)
        b=Source(path=affine_path('workspace','topic'),title='Topic',provider='affine',approved=True)
        s.add_all([a,b]);s.commit();connections.relate(s,b,'Other body.',settings);s.commit()
        row=s.exec(select(SourceRelationship)).one();assert row.state=='suggested' and family(a)!=family(b)
        connections.change_relationship(s,row.id,'linked',0)
        assert family(a)==family(b) and a.approved and b.approved
        connections.change_relationship(s,row.id,'unlinked',1)
        assert family(a)!=family(b)


def test_partial_inventory_resumes_cursor_without_false_missing(client,settings,affine):
    klass=AffineReader;count={'calls':0}
    def transport(req):
        count['calls']+=1
        body=json.loads(req.content)
        if not body['after']:
            return httpx.Response(200,json={'items':[{'id':'a','title':'A','updated_at':'1'}],'complete':False,'cursor':'next'})
        if count['calls']==2: return httpx.Response(503)
        return httpx.Response(200,json={'items':[{'id':'b','title':'B','updated_at':'1'}],'complete':True,'cursor':None})
    reader=klass(settings,httpx.MockTransport(transport));vault=VaultFake();hub=Readers(vault,settings);hub.affine.close();hub.affine=reader
    with Session(client.app.state.engine) as s:
        approve(s);p=auto.policy(s)
        first,ok=hub.scan(s,p,lambda:None)
        assert 'affine' not in ok
        second,ok=hub.scan(s,p,lambda:None)
        assert 'affine' in ok and len([x for x in second if x['path'].startswith('affine:')])==2
    hub.close()


def test_reused_alias_requires_original_remote_provenance(client,settings):
    from app.automatic_worker import views,reuse_extraction
    with Session(client.app.state.engine) as s:
        original=Source(path='space/A.md',title='A',approved=True,state='complete',version=digest('Exact.'))
        original.family_id=original.id;s.add(original)
        old=Version(source_id=original.id,hash=original.version,body='Exact.',etag='',state='complete');s.add(old);s.commit()
        copy=Source(path=affine_path('workspace','a'),title='A',provider='affine',approved=True,family_id=original.id,version=digest('A\n\0Exact.'))
        new=Version(source_id=copy.id,hash=copy.version,body='Exact.',etag='');s.add_all([copy,new]);s.commit()
        canonical_parts=auto.ensure_sections(s,original,old)
        for part in canonical_parts:part.state='reviewed';s.add(part)
        s.commit()
        parts=auto.ensure_sections(s,copy,new);reuse_extraction(s,copy,new,parts);s.commit()
        proxies,versions,documents=views(s,parts)
        memory=MemoryFake()
        memory.docs[canonical_parts[0].document_id]={'document_metadata':{'source_id':original.id,'version':old.hash},'original_text':'# A\n\nExact.'}
        assert memory.provenance(proxies,documents)=={parts[0].id}
        memory.docs[canonical_parts[0].document_id]['document_metadata']['source_id']='unrelated-document'
        with pytest.raises(DomainError,match='remote_document_mismatch'):memory.provenance(proxies,documents)


def test_affine_accepted_retain_recovers_same_operation_after_process_death(client,settings):
    import time
    with Session(client.app.state.engine) as s:
        approve(s)
        source=Source(path=affine_path('workspace','a'),title='A',provider='affine',approved=True,version=digest('A\n\0Original.'))
        version=Version(source_id=source.id,hash=source.version,body='Original.',etag='');s.add_all([source,version]);s.commit()
        unit=auto.ensure_sections(s,source,version)[0]
        memory=MemoryFake();reader=SimpleNamespace(permalink=lambda path:connections.permalink(path),settings=settings)
        memory.on_retain=lambda:(_ for _ in ()).throw(SystemExit('simulated-death'))
        with pytest.raises(SystemExit):automatic_worker.retain_section(s,memory,reader,unit,lambda *args:None,time.monotonic()+10)
        operation=unit.operation_id;assert operation and memory.ops[operation]['status']=='completed'
        memory.on_retain=None
        automatic_worker.retain_section(s,memory,reader,unit,lambda *args:None,time.monotonic()+10)
        assert unit.operation_id==operation and unit.state=='retained'
        assert len([x for x in memory.posts if x[0]=='/memories'])==1


def test_provider_pause_before_retain_keeps_other_provider_enabled(client,settings):
    import time
    with Session(client.app.state.engine) as s:
        approve(s)
        source=Source(path=affine_path('workspace','a'),title='A',provider='affine',approved=True,version=digest('A\n\0Original.'))
        version=Version(source_id=source.id,hash=source.version,body='Original.',etag='');s.add_all([source,version]);s.commit()
        unit=auto.ensure_sections(s,source,version)[0]
        connections.control(s,0,True)
        memory=MemoryFake();reader=SimpleNamespace(permalink=lambda path:connections.permalink(path),settings=settings)
        with pytest.raises(DomainError,match='provider_paused'):
            automatic_worker.retain_section(s,memory,reader,unit,lambda *args:None,time.monotonic()+10)
        assert not unit.operation_id and not memory.posts
        assert connections.scopes(s)['affine']['paused']


def test_hindsight_readiness_prevents_reading_sources(client,settings,adapters):
    vault,memory=adapters
    memory.ready=lambda:(_ for _ in ()).throw(DomainError('hindsight_not_ready',503))
    with Session(client.app.state.engine) as s:rid=activate(s,settings,notes=2)
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).error=='hindsight_not_ready'
        assert not s.exec(select(Source)).all() and not vault.reads


def test_future_affine_document_is_discovered_without_scope_reapproval(client,settings,adapters,affine):
    vault,memory=adapters;vault.files={}
    with Session(client.app.state.engine) as s:approve(s);rid=activate(s,settings,notes=4)
    execute_run(client.app.state.engine,settings,rid)
    affine['files']['future']=('Future note','Future distinct statement.')
    from app.services import enqueue
    with Session(client.app.state.engine) as s:rid2=enqueue(s,'future-document-discovery').id
    execute_run(client.app.state.engine,settings,rid2)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid2).state=='completed'
        assert len(s.exec(select(Source)).all())==3
        assert s.exec(select(IntakeNote).where(IntakeNote.path==affine_path('workspace','future'))).one().state=='processed'
        assert s.get(SourceConnection,'affine').revision==0
        assert auto.summary(s,True)['budget']['notes_used']==3


def test_owner_unlink_is_not_undone_by_future_exact_content(client,settings):
    with Session(client.app.state.engine) as s:
        a=Source(path='space/A.md',title='A',approved=True)
        b=Source(path=affine_path('workspace','a'),title='A',provider='affine',approved=True)
        s.add_all([a,b]);s.commit();connections.relate(s,b,'Text.',settings);s.commit()
        row=s.exec(select(SourceRelationship)).one()
        connections.change_relationship(s,row.id,'linked',0)
        connections.change_relationship(s,row.id,'unlinked',1)
        for source in (a,b):s.add(Version(source_id=source.id,hash=digest('Text.'),body='Text.',etag=''))
        s.commit();connections.relate(s,b,'Text.',settings);connections.relate(s,a,'Text.',settings);s.commit()
        assert family(a)!=family(b)


def test_possible_copies_do_not_imply_independent_evidence_until_separated(client,settings):
    with Session(client.app.state.engine) as s:
        a=Source(path='space/Topic.md',title='Topic',approved=True)
        b=Source(path=affine_path('workspace','topic'),title='Topic',provider='affine',approved=True)
        s.add_all([a,b]);s.commit();connections.relate(s,b,'Different content.',settings);s.commit()
        assert family(a)!=family(b)
        assert connections.evidence_family(s,a)==connections.evidence_family(s,b)
        row=s.exec(select(SourceRelationship)).one()
        connections.change_relationship(s,row.id,'unlinked',0)
        assert connections.evidence_family(s,a)!=connections.evidence_family(s,b)


def test_mutable_legacy_remote_documents_are_not_reused(client,settings):
    with Session(client.app.state.engine) as s:
        a=Source(path='space/A.md',title='A',approved=True,state='complete',version=digest('Exact.'))
        a.family_id=a.id;old=Version(source_id=a.id,hash=a.version,body='Exact.',etag='',state='complete')
        b=Source(path=affine_path('workspace','a'),title='A',provider='affine',family_id=a.id,version=digest('A\n\0Exact.'))
        current=Version(source_id=b.id,hash=b.version,body='Exact.',etag='');s.add_all([a,b,old,current]);s.commit()
        auto.ensure_sections(s,a,old,legacy_complete=True)
        parts=auto.ensure_sections(s,b,current);reuse_extraction(s,b,current,parts)
        assert all(not x.reused_from and x.state=='pending' for x in parts)


def test_unlinking_the_root_copy_splits_the_remaining_family(client,settings):
    with Session(client.app.state.engine) as s:
        a=Source(path=affine_path('workspace','a'),title='A',provider='affine',approved=True)
        b=Source(path='space/A.md',title='A',approved=True,family_id=a.id)
        a.family_id=a.id;s.add_all([a,b]);s.commit()
        row=SourceRelationship(source_id=a.id,target_id=b.id,state='linked',method='exact-content');s.add(row);s.commit()
        connections.change_relationship(s,row.id,'unlinked',0)
        assert family(a)==a.id and family(b)==b.id
        assert connections.evidence_family(s,a)!=connections.evidence_family(s,b)


def test_all_provider_outages_are_not_reported_as_success(client,settings,adapters,affine):
    vault,memory=adapters
    vault.inventory=lambda:(_ for _ in ()).throw(DomainError('silverbullet_unavailable',503))
    affine['failure']=True
    with Session(client.app.state.engine) as s:approve(s);rid=activate(s,settings,notes=2)
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).state=='failed' and s.get(Run,rid).error=='source_connections_unavailable'
        assert not s.exec(select(Version)).all()


def test_renamed_affine_document_keeps_captured_version_title(client,settings,adapters,affine):
    from app.services import enqueue
    vault,memory=adapters;vault.files={}
    with Session(client.app.state.engine) as s:approve(s);rid=activate(s,settings,notes=4)
    execute_run(client.app.state.engine,settings,rid)
    with Session(client.app.state.engine) as s:
        original=s.exec(select(Source).where(Source.path==affine_path('workspace','doc-a'))).one()
        sid,old_hash=original.id,original.version
    affine['files']['doc-a']=('Renamed AFFiNE note',affine['files']['doc-a'][1])
    with Session(client.app.state.engine) as s:rid2=enqueue(s,'renamed-affine-document').id
    execute_run(client.app.state.engine,settings,rid2)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid2).state=='completed'
        current=s.get(Source,sid)
        assert current.title=='Renamed AFFiNE note' and current.version!=old_hash
        assert s.exec(select(Version).where(Version.source_id==sid,Version.hash==old_hash)).one().title=='AFFiNE A'
    r=client.get('/api/v1/xereta/sources/'+sid+'/versions/'+old_hash,headers=owner(client,settings))
    assert r.status_code==200 and r.json()['title']=='AFFiNE A' and r.json()['source']['title']=='Renamed AFFiNE note'


def test_unlink_reused_copy_requires_own_extraction_without_rewriting_capture(client,settings):
    with Session(client.app.state.engine) as s:
        a=Source(path='space/A.md',title='A',approved=True,state='complete',version=digest('Exact.'))
        a.family_id=a.id;old=Version(source_id=a.id,hash=a.version,body='Exact.',etag='',state='complete')
        b=Source(path=affine_path('workspace','a'),title='A',provider='affine',family_id=a.id,version=digest('A\n\0Exact.'),state='complete')
        current=Version(source_id=b.id,hash=b.version,body='Exact.',etag='',state='complete');s.add_all([a,b,old,current]);s.commit()
        originals=auto.ensure_sections(s,a,old)
        for part in originals:part.state='reviewed';s.add(part)
        copies=auto.ensure_sections(s,b,current);reuse_extraction(s,b,current,copies)
        for part in copies:part.state='reviewed';s.add(part)
        row=SourceRelationship(source_id=b.id,target_id=a.id,state='linked',method='exact-content');s.add(row);s.commit()
        connections.change_relationship(s,row.id,'unlinked',0)
        assert all(not x.reused_from and x.state=='pending' and x.document_id==x.id for x in copies)
        assert current.body=='Exact.' and current.hash==b.version and current.state=='pending'
        assert b.error=='source_relationship_changed_requires_retain'
        assert s.get(Artifact,'source-provenance-revision:'+b.id).value['revision']>=1
        assert a.version==old.hash and old.state=='complete'


def test_untitled_affine_document_preserves_original_title_in_capture(settings,affine):
    affine['files']['untitled']=('', 'A useful untitled note.')
    reader=connections.AffineReader(settings)
    try:
        captured=reader.capture(affine_path('workspace','untitled'))
        assert captured.title=='Sem título' and captured.original_title==''
        assert captured.hash==digest('\n\0A useful untitled note.')
    finally:reader.close()


def test_exact_duplicates_inside_affine_are_one_family_but_titles_alone_are_not(client,settings):
    with Session(client.app.state.engine) as s:
        a=Source(path=affine_path('workspace','a'),title='Shared title',provider='affine',approved=True)
        b=Source(path=affine_path('workspace','b'),title='Shared title',provider='affine',approved=True)
        c=Source(path=affine_path('workspace','c'),title='Shared title',provider='affine',approved=True)
        s.add_all([a,b,c]);s.add(Version(source_id=a.id,hash=digest('Original.'),body='Original.',etag=''));s.commit()
        connections.relate(s,b,'Original.',settings);connections.relate(s,c,'A different statement.',settings);s.commit()
        assert family(a)==family(b) and family(c)!=family(a)
        assert len(s.exec(select(SourceRelationship)).all())==1


def test_render_identical_crdt_changes_preserve_original_snapshot_and_manifest(settings,affine):
    from app.services import save_captured_snapshot
    reader=connections.AffineReader(settings)
    try:
        first=reader.capture(affine_path('workspace','doc-a'))
        source=Source(path=first.path,title=first.title,provider='affine')
        version=Version(source_id=source.id,hash=first.hash,body=first.body,etag=first.etag,title=first.title)
        save_captured_snapshot(settings,source,version,first)
        original=settings.state_path/'captures'/source.id/(version.hash+'.bin')
        manifest=original.with_suffix('.json').read_bytes()
        affine['snapshot']=b'same-rendered-text-new-crdt-state'
        second=reader.capture(first.path)
        assert first.hash==second.hash and first.etag!=second.etag
        save_captured_snapshot(settings,source,version,second)
        assert original.read_bytes()==first.snapshot
        assert original.with_suffix('.json').read_bytes()==manifest
        assert version.etag==first.etag
        assert original.with_name(version.hash+'-'+second.etag+'.bin').read_bytes()==second.snapshot
    finally:reader.close()


def test_connection_pause_during_consolidation_stops_before_draft_and_resumes_receipts(client,settings,adapters,affine,monkeypatch):
    from app.services import enqueue
    vault,memory=adapters;vault.files={};calls=[]
    original_draft=automatic_worker.draft
    def counted_draft(*args):calls.append('draft');return original_draft(*args)
    monkeypatch.setattr(automatic_worker,'draft',counted_draft)
    original_call=memory.call;paused=[]
    def call(method,path='',body=None,missing=False):
        result=original_call(method,path,body,missing)
        if method=='POST' and path=='/consolidate' and not paused:
            with Session(client.app.state.engine) as other:connections.control(other,0,True)
            paused.append(True)
        return result
    memory.call=call
    with Session(client.app.state.engine) as s:approve(s);rid=activate(s,settings,notes=2)
    execute_run(client.app.state.engine,settings,rid)
    assert not calls
    with Session(client.app.state.engine) as s:
        assert s.get(Run,rid).state=='completed'
        assert all(x.state=='retained' for x in s.exec(select(IntakeSection)))
        connections.control(s,1,False);next_id=enqueue(s,'resume-paused-provider').id
    execute_run(client.app.state.engine,settings,next_id)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,next_id).state=='completed' and all(x.state=='reviewed' for x in s.exec(select(IntakeSection)))
    assert len(calls)==1
    assert len([path for path,body in memory.posts if path=='/memories'])==2
    assert len([path for path,body in memory.posts if path=='/consolidate'])==1
