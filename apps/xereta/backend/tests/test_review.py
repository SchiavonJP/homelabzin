import json

import pytest
from sqlmodel import Session, select

from test_xereta import client, settings, seed, owner
from app.models import Artifact, Feedback, Finding, Publication, Question, ReviewPage, Source, Version
from app.review import ANSWER_START, ANSWER_END, CHECKS, question_path, publish_review
from app.services import answer_question, request_publication
from app.vault import Capture, DomainError, INBOX, REVIEW_INDEX, digest
from app import sync_check


class VaultStub:
    def __init__(self):
        self.files = {}
        self.fail_after_put = False
        self.on_put = None

    def permalink(self, path):
        return 'https://silverbullet.joaopaulo.me/' + path.removesuffix('.md')

    def capture(self, path):
        if path not in self.files:
            raise DomainError('vault_file_missing', 404)
        body = self.files[path]
        return Capture(path, body, digest(body), '"sha256:' + digest(body) + '"')

    def write_review(self, path, body, etag=None):
        if etag:
            if self.capture(path).etag != etag:
                raise DomainError('vault_revision_conflict')
        elif path in self.files:
            raise DomainError('vault_revision_conflict')
        self.files[path] = body
        if self.on_put:
            self.on_put()
        if self.fail_after_put:
            self.fail_after_put = False
            raise DomainError('publication_readback_changed')
        return self.capture(path)


def test_individual_pages_and_small_index(client, settings):
    settings.publish_enabled = True
    vault = VaultStub()
    with Session(client.app.state.engine) as s:
        source, version, q = seed(s)
        s.add(Finding(key='fact', kind='finding', text='Prazo relatado', reason='Nota', evidence=q.evidence));s.commit()
        result = publish_review(s, settings, vault)
        assert result == {'published': 3, 'conflicts': 0}
        assert question_path(q) in vault.files and REVIEW_INDEX in vault.files
        assert INBOX not in vault.files
        assert 'Minhas notas' not in vault.files[question_path(q)]
        assert '<!--' not in vault.files[question_path(q)]
        assert '## Resposta' not in vault.files[REVIEW_INDEX]
        assert len(s.exec(select(ReviewPage)).all()) == 3
        before = vault.files.copy()
        publish_review(s, settings, vault)
        assert before == vault.files


def test_one_file_conflict_does_not_block_other_answer(client, settings):
    settings.publish_enabled = True
    vault = VaultStub()
    with Session(client.app.state.engine) as s:
        source, version, q = seed(s)
        other = Question(issue='other', text='Outra pergunta?', reason='Contexto', evidence=q.evidence)
        s.add(other);s.commit()
        publish_review(s, settings, vault)
        path = question_path(q)
        vault.files[path] = vault.files[path].replace(ANSWER_START+'\n\n'+ANSWER_END, ANSWER_START+'\nSão 14 dias.\n'+ANSWER_END).replace('- [ ] '+CHECKS['confirm'], '- [x] '+CHECKS['confirm'])
        other_path = question_path(other)
        vault.files[other_path] = vault.files[other_path].replace('Outra pergunta?', 'Uma edição pessoal')
        edited = vault.files[other_path]
        result = publish_review(s, settings, vault)
        assert result['conflicts'] == 1
        assert s.get(Question,q.id).answer == 'São 14 dias.'
        assert s.get(Question,q.id).state == 'resolved'
        assert s.exec(select(Feedback)).one().origin == 'vault'
        assert vault.files[other_path] == edited
        assert s.get(ReviewPage,other_path).error == 'review_context_edited'
        publish_review(s, settings, vault)
        assert len(s.exec(select(Feedback)).all()) == 1


def test_checkbox_cannot_confirm_an_empty_answer(client,settings):
    settings.publish_enabled=True;vault=VaultStub()
    with Session(client.app.state.engine) as s:
        _,_,q=seed(s);publish_review(s,settings,vault)
        path=question_path(q)
        vault.files[path]=vault.files[path].replace('- [ ] '+CHECKS['confirm'],'- [x] '+CHECKS['confirm'])
        result=publish_review(s,settings,vault)
        assert result['conflicts']==1
        assert s.get(Question,q.id).state=='open'
        assert not s.exec(select(Feedback)).all()


def test_publish_recovers_after_put_without_ack(client,settings):
    settings.publish_enabled=True;vault=VaultStub()
    with Session(client.app.state.engine) as s:
        _,_,q=seed(s);vault.fail_after_put=True
        assert publish_review(s,settings,vault)['conflicts']==1
        assert publish_review(s,settings,vault)['conflicts']==0
        assert s.get(ReviewPage,question_path(q)).pending_body==''


def test_previously_published_file_is_not_recreated_after_deletion(client, settings):
    settings.publish_enabled = True
    vault = VaultStub()
    with Session(client.app.state.engine) as s:
        _, _, q = seed(s)
        publish_review(s, settings, vault)
        path = question_path(q)
        del vault.files[path]
        result = publish_review(s, settings, vault)
        assert result['conflicts'] == 1
        assert path not in vault.files
        assert s.get(ReviewPage, path).error == 'vault_file_missing'


def test_concurrent_outbox_generation_is_not_lost(client,settings):
    settings.publish_enabled=True;vault=VaultStub()
    with Session(client.app.state.engine) as s:
        seed(s);request_publication(s);s.commit()
        def race():
            vault.on_put=None
            request_publication(s);s.commit()
        vault.on_put=race
        publish_review(s,settings,vault)
        assert s.get(Artifact,'review:outbox').value['state']=='pending'
        publish_review(s,settings,vault)
        assert s.get(Artifact,'review:outbox').value['state']=='complete'


def test_legacy_file_is_preserved_and_backed_up(client,settings):
    from app.services import render_inbox
    settings.publish_enabled=True;vault=VaultStub()
    with Session(client.app.state.engine) as s:
        seed(s)
        old=render_inbox(s,vault)+'\nAnotação pessoal.\n'
        vault.files[INBOX]=old
        pub=s.get(Publication,1);pub.body=old;s.add(pub);s.commit()
        publish_review(s,settings,vault)
        assert vault.files[INBOX]==old
        assert list((settings.state_path/'legacy-review').glob('*.md'))[0].read_text()==old


def test_resolved_answer_can_be_edited_and_restored(client,settings):
    with Session(client.app.state.engine) as s:
        _,_,q=seed(s)
        answer_question(s,q.id,'14 dias','confirmed',0)
        source=s.exec(select(Source).where(Source.path.startswith('feedback:'))).one()
        old=s.exec(select(Version).where(Version.source_id==source.id)).one()
        old.state='complete';old.operation_id='first-retain';s.add(old);s.commit()
        answer_question(s,q.id,'30 dias','confirmed',1)
        answer_question(s,q.id,'14 dias','confirmed',2)
        s.refresh(old)
        assert old.state=='pending' and not old.operation_id
        assert len(s.exec(select(Feedback)).all())==3
        assert s.get(Question,q.id).revision==3


def test_sync_checkbox_roundtrip_and_order(client,settings):
    vault=VaultStub()
    with Session(client.app.state.engine) as s:
        result=sync_check.start(s,vault);path=result['path'];identifier=result['id']
        assert result['state']=='awaiting_obsidian'
        assert sync_check.verify(s,vault,identifier)['state']=='awaiting_obsidian'
        vault.files[path]=vault.files[path].replace(sync_check.FIRST,sync_check.FIRST.replace('[ ]','[x]')).replace(sync_check.SECOND,sync_check.SECOND.replace('[ ]','[x]'))
        with pytest.raises(DomainError,match='sync_confirmation_order'):sync_check.verify(s,vault,identifier)
        vault.files[path]=vault.files[path].replace(sync_check.SECOND.replace('[ ]','[x]'),sync_check.SECOND)
        assert sync_check.verify(s,vault,identifier)['state']=='awaiting_reply'
        assert 'recebeu sua marcação' in vault.files[path]
        vault.files[path]=vault.files[path].replace(sync_check.SECOND,sync_check.SECOND.replace('[ ]','[x]'))
        assert sync_check.verify(s,vault,identifier)['state']=='passed'


def test_sync_reply_journal_recovers_after_lost_ack(client,settings):
    vault=VaultStub()
    with Session(client.app.state.engine) as s:
        result=sync_check.start(s,vault);path=result['path'];identifier=result['id']
        vault.files[path]=vault.files[path].replace(sync_check.FIRST,sync_check.FIRST.replace('[ ]','[x]'))
        vault.fail_after_put=True
        with pytest.raises(DomainError):sync_check.verify(s,vault,identifier)
        assert sync_check.verify(s,vault,identifier)['state']=='awaiting_reply'


def test_new_mutations_require_owner(client,settings):
    headers={'Authorization':'Bearer '+settings.agent_read_token.get_secret_value()}
    for path in ('/api/v1/xereta/review/sync','/api/v1/xereta/sync-check','/api/v1/xereta/sync-check/00000000-0000-0000-0000-000000000000/verify'):
        assert client.post(path,headers=headers).status_code==403


def test_web_answer_publishes_without_a_digest(client,settings,monkeypatch):
    from app.worker import tick
    from app.models import Run
    settings.publish_enabled=True;vault=VaultStub();vault.close=lambda:None
    monkeypatch.setattr('app.vault.Vault',lambda config:vault)
    with Session(client.app.state.engine) as s:
        _,_,q=seed(s);qid=q.id
    tick(client.app.state.engine,settings)
    response=client.patch('/api/v1/xereta/questions/'+qid,headers=owner(client,settings),
        json={'answer':'14 dias','disposition':'confirmed','expected_revision':0})
    assert response.status_code==200
    tick(client.app.state.engine,settings)
    with Session(client.app.state.engine) as s:
        q=s.get(Question,qid)
        assert '14 dias' in vault.files[question_path(q)]
        assert s.get(ReviewPage,question_path(q)).state=='published'
        assert not s.exec(select(Run)).all()


def test_sync_reply_journal_recovers_before_put(client,settings):
    vault=VaultStub()
    with Session(client.app.state.engine) as s:
        result=sync_check.start(s,vault);path=result['path'];identifier=result['id']
        vault.files[path]=vault.files[path].replace(sync_check.FIRST,sync_check.FIRST.replace('[ ]','[x]'))
        actual_write=vault.write_review
        def fail_once(path,body,etag=None):
            vault.write_review=actual_write
            raise DomainError('silverbullet_unavailable')
        vault.write_review=fail_once
        with pytest.raises(DomainError):sync_check.verify(s,vault,identifier)
        assert sync_check.verify(s,vault,identifier)['state']=='awaiting_reply'


def test_repeated_digest_after_answer_reversion_does_not_retain_again(client,settings,monkeypatch):
    from app.models import Run
    from app.services import execute_run
    retains=[]
    class MemoryStub:
        def __init__(self,config):pass
        def configure(self,policy):pass
        def call(self,method,path,body=None,missing=False):
            return {'operation_id':'consolidation'} if path=='/consolidate' else None
        def retain(self,*args,**kwargs):retains.append(args[0])
        def wait(self,*args,**kwargs):pass
        def verify(self,*args):pass
        def provenance(self,sources):return {x.id for x in sources}
        def close(self):pass
    vault=VaultStub();vault.close=lambda:None;vault.settings=settings
    vault.inventory=lambda:[{'path':'space/Projeto.md'}]
    vault.files['space/Projeto.md']='Guardar 14 dias.'
    monkeypatch.setattr('app.services.Memory',MemoryStub)
    monkeypatch.setattr('app.services.Vault',lambda config:vault)
    monkeypatch.setattr('app.services.draft',lambda *args:[])
    settings.pilot_paths=['space/Projeto.md']
    with Session(client.app.state.engine) as s:
        _,_,q=seed(s)
        answer_question(s,q.id,'14 dias','confirmed',0)
        source=s.exec(select(Source).where(Source.path.startswith('feedback:'))).one()
        old=s.exec(select(Version).where(Version.source_id==source.id)).one()
        old.state='complete';old.operation_id='old';s.add(old);s.commit()
        answer_question(s,q.id,'30 dias','confirmed',1)
        answer_question(s,q.id,'14 dias','confirmed',2)
        a=Run(key='first');s.add(a);s.commit();first=a.id
    execute_run(client.app.state.engine,settings,first)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,first).state=='completed'
        b=Run(key='second');s.add(b);s.commit();second=b.id
    execute_run(client.app.state.engine,settings,second)
    with Session(client.app.state.engine) as s:
        assert s.get(Run,second).state=='completed'
        assert len(retains)==1
        assert len(s.exec(select(Feedback).where(Feedback.state=='superseded')).all())==2


def test_human_annotations_survive_question_update(client,settings):
    settings.publish_enabled=True;vault=VaultStub()
    with Session(client.app.state.engine) as s:
        _,_,q=seed(s);publish_review(s,settings,vault)
        path=question_path(q)
        vault.files[path]+='\nMeu comentário pessoal.\n'
        answer_question(s,q.id,'14 dias','confirmed',0)
        publish_review(s,settings,vault)
        assert vault.files[path].endswith('Meu comentário pessoal.\n')
        assert '14 dias' in vault.files[path]


def test_approved_claim_is_not_reproposed_with_new_citations(client,settings):
    from app.services import store_review
    with Session(client.app.state.engine) as s:
        _,_,q=seed(s)
        accepted=Finding(key='accepted',kind='finding',text='Guardar 14 dias.',reason='Original',state='accepted',revision=1,evidence=q.evidence)
        s.add(accepted);s.commit();fid=accepted.id
        item={'issue':'retention','kind':'finding','text':'Guardar 14 dias.',
              'reason':'Uma nova confirmação do mesmo conhecimento.','evidence':q.evidence}
        store_review(s,[item],'new-feedback')
        assert len(s.exec(select(Finding)).all())==1
        assert s.get(Finding,fid).state=='accepted' and s.get(Finding,fid).revision==1
        item={**item,'text':'Guardar 30 dias.'}
        store_review(s,[item],'different-value')
        assert len(s.exec(select(Finding)).all())==2


def test_existing_duplicate_keeps_reviewed_record_and_history(client,settings):
    from app.services import store_review
    from app.review import render_finding,finding_path
    with Session(client.app.state.engine) as s:
        _,_,q=seed(s)
        accepted=Finding(key='accepted',kind='decision',text='Backup local.',reason='Owner',state='accepted',revision=1,evidence=q.evidence)
        duplicate=Finding(key='duplicate',kind='decision',text='Backup local.',reason='Outra citação',evidence=q.evidence)
        s.add_all([accepted,duplicate]);s.commit();aid=accepted.id;did=duplicate.id
        store_review(s,[],'reconcile-existing')
        assert s.get(Finding,aid).state=='accepted' and s.get(Finding,aid).revision==1
        assert s.get(Finding,did).state=='superseded'
        assert s.get(Artifact,'finding-alias:'+did).value['canonical_id']==aid
        body=render_finding(s,VaultStub(),s.get(Finding,did))
        assert finding_path(accepted).removesuffix('.md') in body
        assert '- [ ]' not in body
        response=client.patch('/api/v1/xereta/findings/'+did,headers=owner(client,settings),
            json={'state':'accepted','expected_revision':0})
        assert response.status_code==409


def test_stale_or_conflicting_reviews_are_not_merged(client,settings):
    from app.services import store_review
    with Session(client.app.state.engine) as s:
        source,version,q=seed(s)
        accepted=Finding(key='accepted',kind='finding',text='Prazo relatado.',reason='Original',state='accepted',evidence=q.evidence)
        s.add(accepted);s.commit()
        source.version='changed';s.add(source);s.commit()
        item={'issue':'retention','kind':'finding','text':'Prazo relatado.','reason':'Nova fonte','evidence':q.evidence}
        store_review(s,[item],'stale-evidence')
        assert len(s.exec(select(Finding)).all())==2
        assert not s.exec(select(Finding).where(Finding.state=='superseded')).all()


def test_claim_identity_preserves_meaningful_whitespace(client,settings):
    from app.services import store_review
    with Session(client.app.state.engine) as s:
        _,_,q=seed(s)
        for index,text in enumerate(('Use "Vault  Name".','Use "Vault Name".')):
            store_review(s,[{'issue':'path','kind':'finding','text':text,'reason':'Path','evidence':q.evidence}],str(index))
        assert len(s.exec(select(Finding)).all())==2
        assert not s.exec(select(Finding).where(Finding.state=='superseded')).all()
