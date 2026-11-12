"""Offline acceptance tests: evidence, retries, feedback and private storage."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import io
import tarfile
import os
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock
import contextlib

spec = importlib.util.spec_from_file_location('curator', Path(__file__).with_name('knowledge-curator.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class FakeHindsight:
    def __init__(self):
        self.docs, self.operations, self.submissions = {}, {}, []
        self.response = None
        self.lose_ack = False
        self.deadline = None
        self.base, self.prefix = 'http://127.0.0.1:8888', '/v1/default/banks/test'

    def document(self, sid):
        return self.docs.get(sid)

    def call(self, method, path='', body=None, missing=False):
        if method in ('PUT', 'PATCH'):
            return {}
        if path.startswith('/operations/'):
            return self.operations.get(path.split('/')[-1])
        if path == '/reflect':
            return self.response
        if path == '/memories/list?limit=100':
            return {'items':[{'id':sid,'fact_type':'world'} for sid in self.docs]}
        if path == '/consolidate':
            self.operations['consolidation']={'status':'completed'}
            return {'operation_id':'consolidation'}
        if path.startswith('/memories/') and method == 'GET':
            return {'document_id': path.split('/')[-1]}
        if path == '/memories':
            oid = body['operation_id']
            self.submissions.append(oid)
            item = body['items'][0]
            self.docs[item['document_id']] = {'id':item['document_id'], 'original_text':item['content'],
                'document_metadata':item['metadata']}
            self.operations[oid] = {'status':'completed'}
            if self.lose_ack:
                self.lose_ack = False
                raise c.CuratorError('hindsight_request_incomplete')
            return {'success':True, 'operation_id':oid}
        raise AssertionError((method,path))


class CuratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = c.Ledger(Path(self.temp.name) / 'state')
        self.remote = FakeHindsight()

    def tearDown(self):
        self.ledger.db.close()
        self.temp.cleanup()

    def register(self, doc='note1', body='Backups stay local. A cloud copy is only a suggestion.', title='Homelab'):
        return self.ledger.register('https://affine.joaopaulo.me','workspace',doc,title,body.encode())

    def response(self, source, kind='question'):
        return {'structured_output': {'items':[{'issue':'backup-location','kind':kind,
            'text':'Should cloud backups be approved?', 'reason':'Clarify the pending suggestion.',
            'evidence':[{'source_id':source['id'],'quote':'Backups stay local.'}]}]},
            'based_on':{'memories':[{'id':source['id']}]}}

    def test_registration_is_stable_and_keeps_raw_capture(self):
        a, b = self.register(), self.register()
        self.assertEqual(a,b)
        self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM versions').fetchone()[0],1)
        capture = next((self.ledger.root/'captures').rglob('*.md'))
        self.assertIn(b'Backups stay local.',capture.read_bytes())
        self.assertEqual(capture.stat().st_mode & 0o777,0o600)

    def test_unchanged_capture_updates_freshness_without_rewriting_version_history(self):
        with patch.object(c,'now',return_value='2026-11-05T12:00:00+00:00'):
            self.register()
        meta=next((self.ledger.root/'captures').rglob('*.json'))
        original=meta.read_bytes()
        with patch.object(c,'now',return_value='2026-11-06T12:00:00+00:00'):
            self.register()
        self.assertEqual(meta.read_bytes(),original)
        source=self.ledger.current()[0]
        self.assertEqual(source['captured'],'2026-11-05T12:00:00+00:00')
        self.assertEqual(source['last_checked'],'2026-11-06T12:00:00+00:00')

    def test_title_change_is_a_new_version(self):
        first = self.register()
        second = self.register(title='Renamed Homelab')
        self.assertEqual(first['source_id'],second['source_id'])
        self.assertNotEqual(first['version'],second['version'])
        self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM versions').fetchone()[0],2)

    def test_edited_body_creates_a_version_without_replacing_the_original_capture(self):
        original = 'Backups stay local. A cloud copy is only a suggestion.'
        edited = 'Backups stay local. Retention is still an open question.'
        first = self.register(body=original)
        second = self.register(body=edited)
        self.assertEqual(first['source_id'], second['source_id'])
        self.assertNotEqual(first['version'], second['version'])
        rows = self.ledger.db.execute('SELECT version,body FROM versions').fetchall()
        self.assertEqual({row['body'] for row in rows}, {original, edited})
        self.assertEqual(self.ledger.current()[0]['version'], second['version'])
        archived = {path.read_text() for path in (self.ledger.root/'captures').rglob('*.md')}
        self.assertEqual(archived, {original, edited})
        self.assertEqual(self.register(body=edited), second)
        self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM versions').fetchone()[0], 2)

    def test_newlines_normalize_but_meaningful_whitespace_survives(self):
        a=self.register(body='a\r\nb\r\n')
        b=self.register(body='a\nb\n')
        d=self.register(body='a \nb\n')
        self.assertEqual(a['version'],b['version'])
        self.assertNotEqual(b['version'],d['version'])

    def test_duplicate_import_requires_alias_and_alias_is_not_ingested(self):
        first=self.register()
        with self.assertRaisesRegex(c.CuratorError,'register_as_alias'):
            self.register(doc='mirror')
        self.ledger.register('https://affine.joaopaulo.me','workspace','mirror','Homelab',
            b'Backups stay local. A cloud copy is only a suggestion.',first['source_id'])
        self.assertEqual(len(self.ledger.current()),1)

    def test_alias_cannot_change_identity_silently(self):
        first=self.register()
        with self.assertRaisesRegex(c.CuratorError,'migration'):
            self.ledger.register('https://affine.joaopaulo.me','workspace','note1','Homelab',b'x',kind='feedback')

    def test_generated_sources_are_excluded(self):
        for title,body in [('_AgentKnowledge Index','x'),('Index','---\ngenerated: true\n---\nx'),
                           ('Open Questions','export removed the frontmatter')]:
            with self.assertRaisesRegex(c.CuratorError,'generated_source'):
                self.register(title=title,body=body)

    def test_large_notes_are_visible_and_not_truncated(self):
        self.register(body='x'*(c.MAX_PROCESS+1))
        source=self.ledger.current()[0]
        self.assertEqual(source['state'],'oversized')
        self.assertEqual(len(source['body']),c.MAX_PROCESS+1)

    def test_capture_cannot_replace_an_inflight_document(self):
        self.register()
        c.process_source(self.ledger,self.remote,self.ledger.current()[0],float('inf'))
        with self.assertRaisesRegex(c.CuratorError,'still_processing'):
            self.register(body='different')

    def test_lost_ack_reconciles_without_duplicate_submission(self):
        self.register()
        self.remote.lose_ack=True
        with self.assertRaises(c.CuratorError):
            c.process_source(self.ledger,self.remote,self.ledger.current()[0],float('inf'))
        c.process_source(self.ledger,self.remote,self.ledger.current()[0],float('inf'))
        self.assertEqual(self.ledger.current()[0]['state'],'complete')
        self.assertEqual(len(self.remote.submissions),1)

    def test_missing_operation_replays_identical_idempotency_key(self):
        self.register()
        c.process_source(self.ledger,self.remote,self.ledger.current()[0],float('inf'))
        self.remote.operations.clear()
        self.remote.docs.clear()
        c.process_source(self.ledger,self.remote,self.ledger.current()[0],float('inf'))
        self.assertEqual(len(set(self.remote.submissions)),1)

    def test_completed_operation_requires_exact_document_readback(self):
        self.register()
        c.process_source(self.ledger,self.remote,self.ledger.current()[0],float('inf'))
        self.remote.docs[self.ledger.current()[0]['id']]['original_text']='tampered'
        with self.assertRaisesRegex(c.CuratorError,'mismatch'):
            c.process_source(self.ledger,self.remote,self.ledger.current()[0],float('inf'))

    def test_unfinished_operation_does_not_submit_again(self):
        self.register()
        c.process_source(self.ledger,self.remote,self.ledger.current()[0],float('inf'))
        for value in self.remote.operations.values(): value['status']='pending'
        c.process_source(self.ledger,self.remote,self.ledger.current()[0],float('inf'))
        self.assertEqual(len(self.remote.submissions),1)

    def test_failed_operation_is_held_for_explicit_retry(self):
        self.register()
        c.process_source(self.ledger,self.remote,self.ledger.current()[0],float('inf'))
        for value in self.remote.operations.values(): value['status']='failed'
        with self.assertRaisesRegex(c.CuratorError,'failed'):
            c.process_source(self.ledger,self.remote,self.ledger.current()[0],float('inf'))
        self.assertEqual(self.ledger.current()[0]['state'],'failed')

    def test_dry_run_never_calls_remote(self):
        self.register()
        with patch.object(self.remote,'call',side_effect=AssertionError('network')):
            result=c.run(self.ledger,self.remote,{},dry=True)
        self.assertEqual(result['status'],'preview')

    def test_valid_citation_uses_capture_version(self):
        self.register()
        source=self.ledger.current()[0]
        items=c.validate_review(self.response(source),[source],{source['id']})
        self.assertEqual(items[0]['evidence'][0]['version'],source['version'])

    def test_model_citation_must_appear_in_server_provenance(self):
        self.register()
        source=self.ledger.current()[0]
        with self.assertRaisesRegex(c.CuratorError,'server_evidence'):
            c.validate_review(self.response(source),[source],set())

    def test_invented_quote_is_rejected(self):
        self.register()
        source=self.ledger.current()[0]
        response=self.response(source)
        response['structured_output']['items'][0]['evidence'][0]['quote']='Cloud backups are approved.'
        with self.assertRaisesRegex(c.CuratorError,'quotation'):
            c.validate_review(response,[source],{source['id']})

    def test_invalid_output_types_do_not_publish(self):
        self.register()
        source=self.ledger.current()[0]
        for value in (None, [], {'items':None}, {'items':[None]}):
            with self.assertRaises(c.CuratorError):
                c.validate_review({'structured_output':value},[source],{source['id']})

    def test_multiple_facts_are_one_source(self):
        self.register()
        source=self.ledger.current()[0]
        response=self.response(source)
        response['structured_output']['items'][0]['evidence']*=2
        items=c.validate_review(response,[source],{source['id']})
        self.assertEqual(items[0]['independent_sources'],1)

    def test_question_answer_roundtrip_is_idempotent_and_keeps_human_notes(self):
        self.register()
        source=self.ledger.current()[0]
        self.remote.response=self.response(source)
        items=c.build_review(self.ledger,self.remote,[source])
        output=Path(c.render(self.ledger,items))
        original=(output/'Open Questions.md').read_text()
        q=self.ledger.db.execute('SELECT id FROM questions').fetchone()[0]
        edited=original.replace('### Answer '+q+'\n\n','### Answer '+q+'\n\nKeep backups local.\n')
        edited+='\nMy unrelated human note.\n'
        result=c.feedback(self.ledger,'https://affine.joaopaulo.me/workspace/workspace/review',edited.encode())
        again=c.feedback(self.ledger,'https://affine.joaopaulo.me/workspace/workspace/review',edited.encode())
        self.assertEqual((result['captured_answers'],again['captured_answers']),(1,0))
        question=self.ledger.db.execute('SELECT * FROM questions').fetchone()
        self.assertEqual(question['state'],'answered')
        self.assertEqual(question['disposition'],'tentative')
        archived=next((self.ledger.root/'feedback').glob('*.md')).read_text()
        self.assertIn('My unrelated human note.',archived)
        self.assertEqual((output/'Open Questions.md').read_text(),original)

    def test_backup_restores_ledger(self):
        self.register()
        result=c.backup(self.ledger)
        self.assertEqual(c.digest(Path(result['archive']).read_bytes()),result['sha256'])
        with sqlite3.connect(Path(result['archive']).parent/'ledger.sqlite3') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sources').fetchone()[0],1)
        restored=c.verify_backup(result['archive'],Path(result['archive']).parent/'manifest.json',
                                 Path(self.temp.name)/'restored')
        self.assertEqual(restored['status'],'restore_verified')

    def test_full_run_and_unchanged_rerun_make_one_remote_submission(self):
        self.register()
        self.remote.response=self.response(self.ledger.current()[0])
        with patch.object(c.time,'sleep'):
            first=c.run(self.ledger,self.remote,{},seconds=30)
            second=c.run(self.ledger,self.remote,{},seconds=30)
        self.assertEqual((first['status'],second['status']),('review_ready','review_ready'))
        self.assertEqual(len(self.remote.submissions),1)
        self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM questions').fetchone()[0],1)

    def test_reflection_outage_keeps_completed_ingestion_and_renders_pending(self):
        self.register()
        self.remote.response=self.response(self.ledger.current()[0])
        original=self.remote.call
        def fail_reflection(method,path='',body=None,missing=False):
            if path=='/reflect': raise c.CuratorError('hindsight_http_500')
            return original(method,path,body,missing)
        with patch.object(self.remote,'call',side_effect=fail_reflection),patch.object(c.time,'sleep'):
            with self.assertRaisesRegex(c.CuratorError,'500'):
                c.run(self.ledger,self.remote,{},seconds=30)
        self.assertEqual(self.ledger.current()[0]['state'],'complete')
        output=Path(self.ledger.artifact('latest_review'))
        self.assertIn('Review is incomplete',(output/'Pending Digest.md').read_text())

    def test_gateway_draft_has_server_provenance_and_one_bounded_model_request(self):
        self.register()
        source=self.ledger.current()[0]
        c.process_source(self.ledger,self.remote,source,float('inf'))
        payload={'choices':[{'finish_reason':'stop','message':{'content':c.dumps(self.response(source)['structured_output'])}}],
                 'model':'ufsc-vision'}
        response=Mock();response.read.return_value=c.dumps(payload).encode()
        opener=Mock();opener.open.return_value=contextlib.nullcontext(response)
        with patch.dict(os.environ,{'LITELLM_API_KEY':'private-test-key'}),patch.object(c.urllib.request,'build_opener',return_value=opener):
            result=c.GatewayDraft().draft(self.remote,[source],'Preserve conflicts.')
        self.assertIn(source['id'],c.trusted_sources(self.remote,result))
        self.assertEqual(len(c.validate_review(result,[source],{source['id']})),1)
        opener.open.assert_called_once()
        body=json.loads(opener.open.call_args.args[0].data)
        self.assertEqual(body['model'],'ufsc-vision')
        self.assertEqual(body['reasoning_effort'],'none')
        self.assertNotIn('private-test-key',c.dumps(result))

    def test_gateway_draft_requires_verified_remote_documents(self):
        self.register()
        source=self.ledger.current()[0]
        with patch.dict(os.environ,{'LITELLM_API_KEY':'private-test-key'}),patch.object(c.urllib.request,'build_opener') as network:
            with self.assertRaisesRegex(c.CuratorError,'sources_not_verified'):
                c.GatewayDraft().draft(self.remote,[source],'Preserve conflicts.')
        network.assert_not_called()

    def test_editorial_review_replaces_unanswered_drafts_without_inventing_owner_approval(self):
        self.register()
        c.process_source(self.ledger,self.remote,self.ledger.current()[0],float('inf'))
        c.process_source(self.ledger,self.remote,self.ledger.current()[0],float('inf'))
        source=self.ledger.current()[0]
        self.remote.response=self.response(source)
        c.build_review(self.ledger,self.remote,[source])
        candidate=self.response(source)['structured_output']
        candidate['items'][0]['issue']='current-implementation-status'
        candidate['items'][0]['text']='Which ideas are deployed and which are candidates?'
        c.edit_review(self.ledger,self.remote,candidate)
        states=dict(self.ledger.db.execute('SELECT issue,state FROM questions'))
        self.assertEqual(states,{'backup-location':'withdrawn','current-implementation-status':'open'})
        with patch.object(self.remote,'call',side_effect=AssertionError('editorial review must survive rerun')):
            self.assertEqual(c.build_review(self.ledger,self.remote,[source])[0]['text'],candidate['items'][0]['text'])
        self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM feedback').fetchone()[0],0)

    def test_editorial_revision_preserves_answered_questions(self):
        self.register()
        source=self.ledger.current()[0]
        self.remote.response=self.response(source)
        c.build_review(self.ledger,self.remote,[source])
        self.ledger.db.execute("UPDATE questions SET answer='Owner text',state='answered'")
        self.ledger.db.commit()
        c.save_questions(self.ledger,[],replace=True)
        row=self.ledger.db.execute('SELECT answer,state FROM questions').fetchone()
        self.assertEqual(tuple(row),('Owner text','answered'))

    def test_review_binding_cannot_point_at_an_original(self):
        self.register()
        publication={'pages':{name:'https://affine.joaopaulo.me/workspace/workspace/page'+str(i)
                              for i,name in enumerate(c.PAGES)},'evidence':{}}
        c.bind_review(self.ledger,publication)
        self.assertEqual(self.ledger.artifact('feedback_page'),publication['pages']['Open Questions'])
        publication['pages']['Knowledge Index']=self.ledger.current()[0]['permalink']
        with self.assertRaisesRegex(c.CuratorError,'must_not_target_original'):
            c.bind_review(self.ledger,publication)

    def test_confirmation_creates_separate_owner_feedback_source(self):
        self.register()
        self.remote.response=self.response(self.ledger.current()[0])
        c.build_review(self.ledger,self.remote,self.ledger.current())
        q=self.ledger.db.execute('SELECT id FROM questions').fetchone()[0]
        page='https://affine.joaopaulo.me/workspace/workspace/feedback-page'
        body=f'# Open Questions\n\n### Answer {q}\n\nLocal only.\n\n### Disposition {q}\n\nconfirmed\n\n### End {q}\n'
        c.feedback(self.ledger,page,body.encode())
        qrow=self.ledger.db.execute('SELECT state,disposition FROM questions').fetchone()
        self.assertEqual(tuple(qrow),('resolved','confirmed'))
        answer=[s for s in self.ledger.current() if s['kind']=='feedback'][0]
        self.assertEqual(answer['permalink'],page)
        self.assertIn('Owner disposition: confirmed',answer['body'])
        self.assertNotIn('decision-approved',answer['body'])

    def test_unknown_answer_is_not_ingested(self):
        result=c.feedback(self.ledger,'https://affine.joaopaulo.me/workspace/workspace/page',
            b'# Open Questions\n### Answer q-invented\nCloud approved\n### Disposition q-invented\nconfirmed\n### End q-invented\n')
        self.assertEqual(result['captured_answers'],0)
        self.assertEqual(self.ledger.current(),[])

    def test_incomplete_live_capture_keeps_last_good_version(self):
        first=self.register()
        manifest=Path(self.temp.name)/'manifest.json'
        manifest.write_text(c.dumps({'version':1,'documents':[{'id':'note1','complete':False}]}))
        result=c.register_batch(self.ledger,manifest)
        self.assertEqual(result['sources'][0]['state'],'incomplete')
        self.assertEqual(self.ledger.current()[0]['version'],first['version'])

    def test_changed_live_capture_requires_checksum(self):
        manifest=Path(self.temp.name)/'manifest.json'
        (manifest.parent/'note.md').write_text('content')
        manifest.write_text(c.dumps({'version':1,'server':'https://affine.joaopaulo.me','workspace':'workspace',
            'documents':[{'id':'note','title':'Title','complete':True,'markdown':'note.md','markdown_sha256':'wrong'}]}))
        with self.assertRaisesRegex(c.CuratorError,'checksum'):
            c.register_batch(self.ledger,manifest)

    def test_missing_consolidation_ack_does_not_blindly_retry(self):
        self.register()
        sources=self.ledger.current()
        key='consolidation:'+c.digest(c.dumps([(s['id'],s['version']) for s in sources]))
        self.ledger.artifact(key,{'state':'submitting'})
        with patch.object(self.remote,'call',side_effect=AssertionError('must reconcile')):
            with self.assertRaisesRegex(c.CuratorError,'acknowledgement_missing'):
                c.consolidate(self.ledger,self.remote,sources,float('inf'))

    def test_restore_rejects_symlinks_and_traversal(self):
        archive=Path(self.temp.name)/'malicious.tar.gz'
        with tarfile.open(archive,'w:gz') as bundle:
            info=tarfile.TarInfo('../escaped')
            info.size=1
            bundle.addfile(info,io.BytesIO(b'x'))
        manifest=archive.with_suffix('.json')
        manifest.write_text(c.dumps({'archive_sha256':c.digest(archive.read_bytes()),'files':{'../escaped':c.digest(b'x')}}))
        with self.assertRaisesRegex(c.CuratorError,'invalid_restore_path'):
            c.verify_backup(archive,manifest,Path(self.temp.name)/'restore')

    def test_status_remains_readable_while_writer_is_running(self):
        with self.ledger.lock():
            with patch.object(c.sys,'stdout',new=io.StringIO()):
                self.assertEqual(c.main(['--state',str(self.ledger.root),'status']),0)

    def test_non_allowlisted_origins_and_ids_are_rejected(self):
        for server in ('https://evil.test','https://u:p@affine.joaopaulo.me','https://affine.joaopaulo.me/?token=x'):
            with self.assertRaises(c.CuratorError):
                self.ledger.register(server,'workspace','note','title',b'content')
        with self.assertRaises(c.CuratorError): c.identifier('../escape')

    def test_symlink_capture_rejected(self):
        path=Path(self.temp.name)/'link'
        path.symlink_to('/etc/hosts')
        with self.assertRaises(OSError): c.read_file(path)

    def test_model_markup_is_escaped(self):
        rendered=c.safe_markdown('<img src=x> [click](https://evil.test)')
        self.assertNotIn('<img',rendered)
        self.assertIn('\\[click\\]',rendered)


if __name__ == '__main__':
    unittest.main()
