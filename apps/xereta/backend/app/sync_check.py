"""Owner-guided Obsidian roundtrip, with two Markdown checkboxes and a server reply."""
from uuid import uuid4

from sqlalchemy import text

from app.models import Artifact, now
from app.vault import DomainError

KEY = 'sync-check:current'
FIRST = '- [ ] Vi esta nota no Obsidian'
SECOND = '- [ ] Recebi a confirmação do Xereta no Obsidian'


def normalized(body):
    for line in (FIRST, SECOND):
        if sum(body.count(line.replace('[ ]', token)) for token in ('[ ]', '[x]', '[X]')) != 1:
            raise DomainError('sync_checkbox_changed')
        body = body.replace(line.replace('[ ]', '[x]'), line).replace(line.replace('[ ]', '[X]'), line)
    return body


def checked(body, line):
    return line.replace('[ ]', '[x]') in body or line.replace('[ ]', '[X]') in body


def status(s):
    item = s.get(Artifact, KEY)
    if not item:
        return {'state': 'not_started'}
    return {k: v for k, v in item.value.items() if k in ('id', 'path', 'state', 'created_at', 'completed_at')}


def save(s, item, **changes):
    item.value = {**item.value, **changes}
    s.add(item); s.commit()


def lock(s):
    if s.bind.dialect.name == 'postgresql':
        s.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 1481855593})


def start(s, vault):
    lock(s)
    item = s.get(Artifact, KEY)
    if item and item.value['state'] not in ('passed', 'creating'):
        return status(s)
    if not item or item.value['state'] == 'passed':
        identifier = str(uuid4())
        body = ('---\ngenerated: true\n---\n\n# Teste de sincronização do Xereta\n\n'
                'No Obsidian, marque a primeira caixa e clique em Verificar no Xereta.\n'
                'Depois que o retorno aparecer aqui, marque a segunda caixa no Obsidian.\n\n'
                + FIRST + '\n' + SECOND + '\n\n## Retorno do Xereta\n\nAguardando sua primeira confirmação.\n\n'
                + '<!-- xereta:sync ' + identifier + ' -->\n')
        item = item or Artifact(key=KEY)
        item.value = {'id': identifier, 'path': 'space/_AgentKnowledge/Sync/obsidian-' + identifier + '.md',
                      'body': body, 'state': 'creating', 'created_at': now()}
        s.add(item); s.commit()
    data = item.value
    try:
        incoming = vault.capture(data['path'])
    except DomainError as error:
        if error.code != 'vault_file_missing':
            raise
        incoming = vault.write_review(data['path'], data['body'])
    if normalized(incoming.body) != normalized(data['body']):
        raise DomainError('sync_note_changed')
    save(s, item, state='awaiting_obsidian')
    return status(s)


def verify(s, vault, identifier):
    lock(s)
    item = s.get(Artifact, KEY)
    if not item or item.value.get('id') != identifier:
        raise DomainError('sync_check_not_found', 404)
    data = item.value
    if data['state'] == 'passed':
        return status(s)
    if data['state'] == 'creating':
        return start(s, vault)
    incoming = vault.capture(data['path'])
    expected = data.get('pending_body') or data['body']
    if data['state'] == 'reply_submitting' and normalized(incoming.body) == normalized(data['body']):
        incoming = vault.write_review(data['path'], expected, incoming.etag)
    if normalized(incoming.body) != normalized(expected):
        raise DomainError('sync_note_changed')
    first, second = checked(incoming.body, FIRST), checked(incoming.body, SECOND)
    if not first:
        if second:
            raise DomainError('sync_confirmation_order')
        return status(s)
    if data['state'] == 'awaiting_obsidian':
        if second:
            raise DomainError('sync_confirmation_order')
        reply = incoming.body.replace('Aguardando sua primeira confirmação.',
            'O Xereta recebeu sua marcação e enviou este retorno em ' + now() + '. Agora marque a segunda caixa no Obsidian.')
        save(s, item, state='reply_submitting', pending_body=reply)
        incoming = vault.write_review(data['path'], reply, incoming.etag)
        save(s, item, state='awaiting_reply', body=incoming.body, pending_body='')
        return status(s)
    if data['state'] == 'reply_submitting':
        # The reply was read back above; a crash after PUT does not send a new reply.
        save(s, item, state='awaiting_reply', body=incoming.body, pending_body='')
    if second:
        save(s, item, state='passed', completed_at=now())
    return status(s)
