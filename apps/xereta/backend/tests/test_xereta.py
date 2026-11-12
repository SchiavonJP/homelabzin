from datetime import UTC, datetime
from pathlib import Path
import secrets

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import Settings
from app.main import create_app
from app.memory import validate_review
from app.models import Feedback, Publication, Question, Run, Schedule, Source, Version
from app.services import answer_question, consume_feedback, due_schedule, enqueue, render_inbox
from app.vault import Capture, DomainError, INBOX, Vault, digest, eligible, source_path


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url='sqlite:///'+str(tmp_path/'db.sqlite3'),
        secret_key=secrets.token_urlsafe(48), owner_password=secrets.token_urlsafe(32),
        agent_read_token=secrets.token_urlsafe(48), state_path=tmp_path)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def owner(client, settings):
    r = client.post('/api/v1/login/access-token', json={'email':settings.owner_email,
        'password':settings.owner_password.get_secret_value()})
    assert r.status_code == 200
    return {'Authorization':'Bearer '+r.json()['access_token']}


def seed(s):
    source = Source(path='space/Projeto.md', title='Projeto', approved=True, version=digest('Guardar 14 dias.'))
    s.add(source)
    version = Version(source_id=source.id, hash=source.version, body='Guardar 14 dias.', etag='"sha256:'+source.version+'"', state='complete')
    s.add(version)
    q = Question(issue='retention',text='Qual prazo vale?',reason='Há um conflito.',
                 evidence=[{'source_id':source.id,'version':source.version,'quote':'Guardar 14 dias.'}])
    s.add(q)
    s.commit()
    return source, version, q


def test_authentication_and_permissions(client, settings):
    assert client.get('/api/v1/curator/overview').status_code == 401
    reader={'Authorization':'Bearer '+settings.agent_read_token.get_secret_value()}
    assert client.get('/api/v1/curator/overview',headers=reader).status_code == 200
    assert client.post('/api/v1/curator/runs',json={'idempotency_key':'test-1234'},headers=reader).status_code == 403
    assert client.post('/mcp/',json={},headers={}).status_code == 401
    assert client.get('/health/live').status_code == 200


def test_idempotency_and_no_overlap(client, settings):
    headers=owner(client,settings)
    a=client.post('/api/v1/curator/runs',json={'idempotency_key':'test-1234'},headers=headers)
    b=client.post('/api/v1/curator/runs',json={'idempotency_key':'test-1234'},headers=headers)
    c=client.post('/api/v1/curator/runs',json={'idempotency_key':'different-run'},headers=headers)
    assert a.status_code == 202 and a.json()['id']==b.json()['id']==c.json()['id']


def test_schedule_gate_cannot_be_overridden_by_browser(client,settings):
    headers=owner(client,settings)
    r=client.put('/api/v1/curator/schedule',headers=headers,json={'enabled':True,'hour':3,'minute':0,'expected_revision':0})
    assert r.status_code == 409 and r.json()['detail']=='acceptance_gates_pending'


def test_answer_revision_and_owner_authority(client,settings):
    headers=owner(client,settings)
    with Session(client.app.state.engine) as s:
        _,_,q=seed(s)
        qid=q.id
    response=client.patch('/api/v1/curator/questions/'+qid,headers=headers,json={
        'answer':'São 14 dias.','disposition':'confirmed','expected_revision':0})
    assert response.status_code==200 and response.json()['state']=='resolved'
    assert response.json()['disposition']!='decision-approved'
    assert client.patch('/api/v1/curator/questions/'+qid,headers=headers,json={
        'answer':'Outra resposta.','disposition':'confirmed','expected_revision':0}).status_code==409
    with Session(client.app.state.engine) as s:
        assert len(s.exec(select(Feedback)).all())==1


def test_changed_evidence_blocks_confirmation(client,settings):
    with Session(client.app.state.engine) as s:
        source,_,q=seed(s)
        source.version=digest('Agora são 30 dias.')
        s.add(source);s.commit()
        with pytest.raises(DomainError,match='question_evidence_changed'):
            answer_question(s,q.id,'14 dias','confirmed',0)


def test_path_boundaries_and_generated_exclusion():
    for path in ('space/../secret.md','space/.obsidian/x.md','/space/a.md','space/a/../../x.md','space/x\\a.md'):
        with pytest.raises(DomainError):source_path(path)
    assert eligible('space/Ideias/ação.md')
    assert not eligible(INBOX) and not eligible('space/Library/thing.md')
    assert not eligible('space/CONFIG.md') and not eligible('space/sync-conflict.md')


def test_adapter_revision_writes_and_fail_closed(settings):
    requests=[]
    body='# Caixa de entrada'
    def handler(req):
        requests.append(req)
        if req.method=='PUT':return httpx.Response(412)
        return httpx.Response(200,text=body,headers={'ETag':'"sha256:'+digest(body)+'"'})
    vault=Vault(settings,httpx.MockTransport(handler))
    assert vault.capture('space/Ideias.md').hash==digest(body)
    with pytest.raises(DomainError,match='vault_revision_conflict'):
        vault.write_inbox(body,'"sha256:'+digest(body)+'"')
    assert requests[-1].headers['If-Match']=='"sha256:'+digest(body)+'"'
    with pytest.raises(DomainError):vault.write_inbox(body)
    assert requests[-1].headers['If-None-Match']=='*'


def test_redirects_and_malformed_inventory_are_not_accepted(settings):
    vault=Vault(settings,httpx.MockTransport(lambda r:httpx.Response(307,headers={'Location':'https://evil.invalid'})))
    with pytest.raises(DomainError,match='silverbullet_http_307'):vault.inventory()
    for url in ('http://evil.invalid','http://192.168.0.12:3011/?token=x','http://user@192.168.0.12:3011'):
        with pytest.raises(ValueError):Settings(**{**settings.model_dump(),'silverbullet_url':url})


def test_quotes_are_exact_and_sources_server_verified(client,settings):
    with Session(client.app.state.engine) as s:
        source,v,q=seed(s)
        item={'issue':'retention','kind':'finding','text':'Prazo relatado','reason':'Nota original',
              'evidence':[{'source_id':source.id,'quote':'Guardar 14 dias.'}]}
        assert validate_review({'items':[item]},[source],{source.id:v},{source.id})[0]['evidence'][0]['version']==v.hash
        with pytest.raises(DomainError):validate_review({'items':[item]},[source],{source.id:v},set())
        item['evidence'][0]['quote']='Guardar 30 dias.'
        with pytest.raises(DomainError):validate_review({'items':[item]},[source],{source.id:v},{source.id})


def test_vault_answers_and_human_notes_survive(client,settings):
    class Stub:
        def permalink(self,path):return 'https://silverbullet.joaopaulo.me/'+path
        def capture(self,path):return self.current
    vault=Stub()
    with Session(client.app.state.engine) as s:
        source,v,q=seed(s)
        original=render_inbox(s,vault)
        pub=s.get(Publication,1);pub.body=original;s.add(pub);s.commit()
        edited=original.replace('### Resposta\n\n','### Resposta\nO prazo é 14 dias.\n').replace('## Minhas notas\n\n','## Minhas notas\n\nNão apagar minha edição.\n')
        vault.current=Capture(INBOX,edited,digest(edited),'"sha256:'+digest(edited)+'"')
        incoming=consume_feedback(s,vault)
        consume_feedback(s,vault)  # interrupted after feedback save, before publication
        new=render_inbox(s,vault,incoming)
        assert 'O prazo é 14 dias.' in new and 'Não apagar minha edição.' in new
        assert s.get(Question,q.id).state=='answered'
        # Other generated edits are held, never silently replaced.
        vault.current.body=edited.replace('Qual prazo vale?','Uma edição pessoal da pergunta')
        with pytest.raises(DomainError,match='inbox_generated_section_edited'):consume_feedback(s,vault)


def test_schedule_latest_missed_only(client,settings):
    settings.acceptance_passed=True
    with Session(client.app.state.engine) as s:
        schedule=s.get(Schedule,1);schedule.enabled=True;s.add(schedule);s.commit()
        job=due_schedule(s,settings,datetime(2026,11,5,13,0,tzinfo=UTC))
        assert job.key=='schedule:2026-11-05T03:00:00-03:00'
        assert due_schedule(s,settings,datetime(2026,11,5,14,0,tzinfo=UTC)) is None
        assert len(s.exec(select(Run)).all())==1


def test_hindsight_url_is_not_duplicated(settings):
    from app.memory import Memory
    seen=[]
    memory=Memory(settings,httpx.MockTransport(lambda r:(seen.append(str(r.url)) or httpx.Response(200,json={'success':True}))))
    memory.call('GET','/operations/test')
    assert seen==['http://127.0.0.1:8888/v1/default/banks/knowledge-vault-pilot/operations/test']
    memory.close()


def test_owner_feedback_is_versioned_and_citable(client,settings):
    from app.services import current_versions, register_feedback, store_review
    from app.models import Finding
    with Session(client.app.state.engine) as s:
        source,v,q=seed(s)
        answer_question(s,q.id,'Escolho 14 dias.','decision-approved',0)
        sources,versions=current_versions(s)
        own=next(x for x in sources if x.path.startswith('feedback:'))
        assert 'Escolho 14 dias.' in versions[own.id].body
        f=s.exec(select(Finding)).one()
        assert f.state=='accepted' and f.evidence[0]['source_id']==own.id
        fb=s.exec(select(Feedback)).one()
        register_feedback(s,fb);s.commit()
        assert len(s.exec(select(Version).where(Version.source_id==own.id)).all())==1
        item={'issue':'fact','kind':'finding','text':'Prazo','reason':'Fonte','evidence':q.evidence}
        store_review(s,[item],'first');store_review(s,[item],'changed-fingerprint')
        assert len(s.exec(select(Finding).where(Finding.kind=='finding')).all())==1


@pytest.mark.parametrize("review_state", ["accepted", "rejected"])
def test_finding_acceptance_is_owner_evidence(client,settings,review_state):
    from app.models import Finding
    with Session(client.app.state.engine) as s:
        source,v,q=seed(s)
        f=Finding(key='fact',kind='finding',text='Guardar 14 dias.',reason='Nota',evidence=q.evidence)
        s.add(f);s.commit();fid=f.id
    r=client.patch('/api/v1/xereta/findings/'+fid,headers=owner(client,settings),
        json={'state':review_state,'expected_revision':0})
    assert r.status_code==200
    with Session(client.app.state.engine) as s:
        fb=s.exec(select(Feedback)).one()
        assert fb.disposition=='confirmed' and fb.origin=='web'
        assert fb.answer.startswith('Descarto') == (review_state=='rejected')
        assert len(s.exec(select(Source).where(Source.path.startswith('feedback:'))).all())==1


def test_only_terminal_remote_failure_is_reset_on_retry(client,settings):
    with Session(client.app.state.engine) as s:
        source,v,q=seed(s)
        v.state='remote_failed';v.operation_id='failed-op';s.add(v)
        unknown=Version(source_id=source.id,hash='unknown',body='Pending',etag='',state='submitted',operation_id='keep-op')
        s.add(unknown)
        run=Run(key='old-failed',state='failed');s.add(run);s.commit();rid=run.id;vid=v.id;uid=unknown.id
    r=client.post('/api/v1/xereta/runs/'+rid+'/retry',headers=owner(client,settings),json={'idempotency_key':'retry-explicit'})
    assert r.status_code==202
    with Session(client.app.state.engine) as s:
        assert s.get(Version,vid).operation_id==''
        assert s.get(Version,uid).operation_id=='keep-op'


def test_schema_version_is_recorded(client,settings):
    from sqlalchemy import text
    with client.app.state.engine.connect() as c:
        assert c.execute(text('select version_num from alembic_version')).scalar()=='0005'


def test_hindsight_missing_operation_envelope(settings):
    from app.memory import Memory
    memory=Memory(settings,httpx.MockTransport(lambda r:httpx.Response(200,json={'status':'not_found'})))
    assert memory.call('GET','/operations/unsubmitted',missing=True) is None
    memory.close()


def test_mcp_allows_deployed_host_and_blocks_unknown_host(client,settings):
    headers={'Authorization':'Bearer '+settings.agent_read_token.get_secret_value(),
             'Accept':'application/json, text/event-stream','Host':'192.168.0.213:3101'}
    body={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26',
          'capabilities':{},'clientInfo':{'name':'gate','version':'1'}}}
    assert client.post('/mcp/',headers=headers,json=body).status_code==200
    headers['Host']='evil.invalid'
    assert client.post('/mcp/',headers=headers,json=body).status_code==421


def test_portuguese_inbox_confirmation_remains_backward_compatible():
    from app.services import answers_from
    qid='12345678-1234-1234-1234-123456789012'
    for shown,canonical in [('confirmada','confirmed'),('decisão aprovada','decision-approved'),('confirmed','confirmed')]:
        body=f'<!-- xereta:question {qid} revision 2 -->\n### Resposta\nResposta.\n### Confirmação\n{shown}\n<!-- xereta:end-question -->'
        assert answers_from(body)[qid]==(2,'Resposta.',canonical)
