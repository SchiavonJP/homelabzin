"""Resumable, owner-reviewed split migration. Originals are never modified."""
import json
import re
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

from sqlmodel import select
from app import references,library_config
from app.karakeep import Karakeep
from app.models import Artifact,ReferenceItem,now,uid
from app.services import save_private
from app.vault import DomainError,digest

PREFIX='space/ReadItLater Inbox/'


def public_manifest(value):
    return {k:v for k,v in value.items() if k!='private_files'}


def load(s,ident):
    if not re.fullmatch(r'[a-f0-9-]{36}',ident):raise DomainError('migration_identity_invalid',422)
    row=s.get(Artifact,'readitlater:'+ident)
    if not row:raise DomainError('migration_not_found',404)
    return row


def preview(s,settings,vault,ident=None):
    if ident:record=load(s,ident)
    else:
        ident=uid();paths=sorted(x['path'] for x in vault.inventory() if x['path'].startswith(PREFIX))
        record=Artifact(key='readitlater:'+ident,value={'id':ident,'created_at':now(),'paths':paths,'cursor':0,'rows':[],
            'complete':False,'revision':0,'private_files':{},'phase':'preview'})
        s.add(record);s.commit()
    value=dict(record.value);rows=list(value['rows']);private=dict(value['private_files'])
    for path in value['paths'][value['cursor']:value['cursor']+40]:
        try:
            cap=vault.capture(path)
            archive=settings.state_path/'readitlater'/ident/'files'/(digest(path)+'.md')
            if not archive.exists():save_private(archive,cap.body)
            elif digest(archive.read_bytes())!=cap.hash:raise DomainError('migration_archive_changed')
            private[path]={'hash':cap.hash,'archive':str(archive)}
            chosen,original_title=references.primary_link(cap.body)
            host=urlsplit(chosen).hostname if chosen else ''
            target='reference' if host=='github.com' or '/read/' in path else 'karakeep' if chosen else ''
            rows.append({'id':digest(path),'path':path,'hash':cap.hash,'title':original_title or Path(path).stem,'url':chosen,
                         'suggested_target':target,'target':target,'state':'pending','reason':'review_required' if chosen else 'primary_url_required','error':''})
        except DomainError as e:
            rows.append({'id':digest(path),'path':path,'url':'','title':Path(path).stem,'target':'','suggested_target':'','state':'exception','reason':e.code,'error':e.code})
        value['cursor']+=1
    value.update(rows=rows,private_files=private,complete=value['cursor']>=len(value['paths']),revision=value['revision']+1)
    record.value=value;s.add(record);s.commit();return public_manifest(value)


def classify(s,ident,decisions,expected):
    from app.automation import lock
    lock(s);record=load(s,ident);value=dict(record.value)
    if value['revision']!=expected:raise DomainError('migration_revision_conflict')
    rows=[dict(x) for x in value['rows']];lookup={x['id']:x for x in rows}
    for decision in decisions:
        row=lookup.get(decision['id'])
        if not row or row['state'] in ('completed','submitting','unknown'):raise DomainError('migration_item_locked')
        if decision['target'] not in ('reference','karakeep','keep'):raise DomainError('migration_target_invalid',422)
        url=references.public_url(decision['url']) if decision['target']!='keep' else row.get('url','')
        row.update(url=url,target=decision['target'],state='classified',error='')
    value.update(rows=rows,revision=expected+1);record.value=value;s.add(record);s.commit();return public_manifest(value)


def apply(s,settings,vault,ident,ids,expected):
    from app.db import worker_lock
    with worker_lock(s.bind) as acquired:
        if not acquired:raise DomainError('migration_worker_busy')
        return _apply(s,settings,vault,ident,ids,expected)


def _apply(s,settings,vault,ident,ids,expected):
    from app.automation import lock
    lock(s);record=load(s,ident);value=dict(record.value)
    if value['revision']!=expected:raise DomainError('migration_revision_conflict')
    if not ids or len(ids)>5:raise DomainError('migration_small_batch_required',422)
    rows=[dict(x) for x in value['rows']];selected=[x for x in rows if x['id'] in ids]
    if len(selected)!=len(set(ids)):raise DomainError('migration_item_invalid',422)
    if any(x['state'] not in ('classified','completed') for x in selected):raise DomainError('migration_classification_required')
    if any(x['target']=='karakeep' for x in selected):
        cfg=library_config.current(s)
        if not cfg.karakeep_inbox_list or cfg.karakeep_inbox_list==cfg.karakeep_ready_list:raise DomainError('migration_inbox_required',422)
        with closing(Karakeep(settings)) as keep:keep.require_manual(cfg.karakeep_inbox_list)
    # Reserve only the requested operation; ambiguous remote writes are held for reconciliation.
    value.update(rows=rows,revision=expected+1);record.value=value;s.add(record);s.commit()
    for row in selected:
        if row['state']=='completed':continue
        if row['target']=='keep':row['state']='completed';row['destination']='original';continue
        current=vault.capture(row['path'])
        if current.hash!=row['hash']:row['state']='exception';row['error']='migration_source_changed';continue
        item=references.item_url(s,row['url'],row['title']);s.commit();s.refresh(item)
        if row['target']=='reference':
            path='space/Referências/'+item.id+'.md'
            body='---\nxereta_type: reference\nxereta_id: '+item.id+'\ntags: []\n---\n\n# '+row['title'].replace('\n',' ')+'\n\nURL: <'+row['url']+'>\n\n'
            body+='Origem preservada: '+references.wiki(row['path'],row['title'],path)+'\n\nVersão original: `'+row['hash']+'`\n\nReferência migrada; leitura e digestão não confirmadas.\n'
            receipt=s.get(Artifact,'migration-reference:'+row['id'])
            if not receipt:
                receipt=Artifact(key='migration-reference:'+row['id'],value={'path':path,'hash':digest(body)});s.add(receipt);s.commit()
            try:
                existing=vault.capture(path)
                if existing.body!=body:raise DomainError('migration_destination_changed')
            except DomainError as e:
                if e.code!='vault_file_missing':raise
                vault.create_reference(path,body)
            references.extract(s,path,body)
            row['destination']=path;row['reference_id']=item.id;row['state']='completed'
        else:
            row['state']='submitting';value['rows']=rows;record.value={**value};s.add(record);s.commit()
            try:
                with closing(Karakeep(settings)) as keep:
                    # The API returns an existing bookmark for an existing URL. Do not PATCH it.
                    result=keep.create_bookmark(row['url'],row['title'],'Origem preservada: '+row['path']+'\nSHA256: '+row['hash'])
                    bookmark=keep.identifier(result['id'])
                    keep.add_to_inbox(bookmark,cfg.karakeep_inbox_list)
                item.bookmark_id=bookmark;s.add(item);s.commit()
                row.update(state='completed',destination='karakeep:'+bookmark,reference_id=item.id)
            except DomainError as e:row.update(state='unknown',error='migration_remote_acknowledgement_unknown')
        value.update(rows=rows);record.value={**value};s.add(record);s.commit()
    value.update(rows=rows);record.value={**value};s.add(record);s.commit();return public_manifest(value)
