"""Independent review notes. Each file has its own CAS journal and conflict boundary."""
import json
import re
import unicodedata
from pathlib import Path
from uuid import uuid4

from sqlmodel import select

from app.models import Artifact, Finding, Publication, Question, ReviewPage, Source, now
from app.vault import DomainError, INBOX, REVIEW_INDEX, digest

BEGIN, END = '<!-- xereta:generated:start -->', '<!-- xereta:generated:end -->'
ANSWER_START, ANSWER_END = '\n## Resposta\n', '\n## Revisão\n'
OLD_ANSWER_START, OLD_ANSWER_END = '<!-- xereta:answer:start -->', '<!-- xereta:answer:end -->'
FOOTER = '\n\n[Revisar no Xereta](http://192.168.0.213:3101/)\n'
CHECKS = {
    'confirm': 'Confirmar esta resposta',
    'decision': 'Registrar como decisão explícita',
    'defer': 'Adiar esta pergunta',
    'accept': 'Confirmar este conhecimento',
    'approve': 'Aprovar esta decisão',
    'reject': 'Descartar',
}
STATES = {'open': 'Aberta', 'answered': 'Rascunho', 'resolved': 'Respondida', 'deferred': 'Adiada',
          'proposed': 'Para revisar', 'accepted': 'Confirmado', 'rejected': 'Descartado'}


def slug(text):
    value = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', value).strip('-')[:64].strip('-') or 'item'


def question_path(q):
    return f'space/_AgentKnowledge/Perguntas/{slug(q.issue)}-{q.id[:8]}.md'


def finding_path(f):
    return f'space/_AgentKnowledge/Conhecimento/{slug(f.text)}-{f.id[:8]}.md'


def source_permalink(s, vault, source):
    if source.path.startswith('reference:'):
        return source.permalink
    if source.path.startswith('affine:'):
        from app.connections import permalink
        return permalink(source.path)
    if source.path.startswith('space/'):
        return vault.permalink(source.path)
    entity = source.path.removeprefix('feedback:')
    if entity.startswith('finding:'):
        item = s.get(Finding, entity.removeprefix('finding:'))
        path = finding_path(item) if item else REVIEW_INDEX
    else:
        item = s.get(Question, entity)
        path = question_path(item) if item else REVIEW_INDEX
    return vault.permalink(path)


def section(body):
    if BEGIN in body:
        if body.count(BEGIN) != 1 or body.count(END) != 1:
            raise DomainError('review_markers_changed')
        return body.split(BEGIN)[1].split(END)[0]
    if body.count(FOOTER) != 1:
        raise DomainError('review_footer_changed')
    return body.split(FOOTER)[0]


def answer_parts(body):
    if OLD_ANSWER_START in body:
        if body.count(OLD_ANSWER_START) != 1 or body.count(OLD_ANSWER_END) != 1:
            raise DomainError('review_answer_section_changed')
        left, tail = body.split(OLD_ANSWER_START)
        value, right = tail.split(OLD_ANSWER_END)
        return left + OLD_ANSWER_START, value, OLD_ANSWER_END + right
    if ANSWER_START not in body or ANSWER_END not in body:
        raise DomainError('review_answer_section_changed')
    left, tail = body.split(ANSWER_START, 1)
    value, separator, right = tail.rpartition(ANSWER_END)
    if not separator:
        raise DomainError('review_answer_section_changed')
    return left + ANSWER_START, value, ANSWER_END + right


def answer(body):
    if BEGIN in body or FOOTER in body:
        body = section(body)
    return answer_parts(body)[1].strip()


def checkbox(body, key):
    if BEGIN in body or FOOTER in body:
        body = section(body)
    if ANSWER_START in body or OLD_ANSWER_START in body:
        left, _, right = answer_parts(body)
        body = left + right
    matches = re.findall(r'^- \[([ xX])\] ' + re.escape(CHECKS[key]) + r'$', body, re.M)
    if len(matches) != 1:
        raise DomainError('review_checkbox_changed')
    return matches[0].lower() == 'x'


def mask(body):
    if ANSWER_START in body or OLD_ANSWER_START in body:
        left, _, right = answer_parts(body)
        body = left + '<answer>' + right
    for label in CHECKS.values():
        body = re.sub(r'^- \[[ xX]\] ' + re.escape(label) + r'$', '- [ ] ' + label, body, flags=re.M)
    return body


def tick(key, checked):
    return f"- [{'x' if checked else ' '}] {CHECKS[key]}"


def wrap(content, incoming=None, entity_id=None, revision=0):
    metadata = f"xereta_id: {entity_id}\nxereta_revision: {revision}\n" if entity_id else ''
    tail = ''
    if incoming:
        section(incoming.body)
        if BEGIN in incoming.body:
            prefix, tail = incoming.body.split(BEGIN)[0], incoming.body.split(END)[1]
            prefix = prefix.removeprefix('---\ngenerated: true\n---\n\n')
            tail = prefix + tail
        else:
            tail = incoming.body.split(FOOTER)[1]
    return '---\ngenerated: true\n' + metadata + '---\n\n' + content + FOOTER + tail


def revision_of(body, kind):
    if BEGIN in body:
        matches = re.findall(r'<!-- xereta:' + kind + r' [a-f0-9-]{36} revision (\d+) -->', body)
    else:
        matches = re.findall(r'^xereta_revision: (\d+)$', body, re.M)
    if len(matches) != 1:
        raise DomainError('review_revision_changed')
    return int(matches[0])


def citations(s, vault, items, page=REVIEW_INDEX):
    from app.services import safe
    lines = []
    for evidence in items:
        source = s.get(Source, evidence['source_id'])
        from app.references import wiki
        link=wiki(source.path,source.title,page) if source.path.startswith('space/') else f'[{safe(source.title)}]({source_permalink(s,vault,source)})'
        lines += [f"- {link} · versão `{evidence['version'][:12]}`",
                  '> ' + safe(evidence['quote']).replace('\n', '\n> ')]
    return '\n'.join(lines)


def render_question(s, vault, q, incoming=None):
    from app.services import safe
    content = '\n'.join([
        '# ' + safe(q.text), '', '**Estado:** ' + STATES.get(q.state, q.state), '',
        ANSWER_START + '\n' + q.answer + '\n' + ANSWER_END, '',
        tick('confirm', q.disposition in ('confirmed', 'decision-approved')),
        tick('decision', q.disposition == 'decision-approved'),
        tick('defer', q.state == 'deferred'), '',
        'Confirmar uma resposta não aprova uma decisão.', '',
        '## Contexto', '', safe(q.reason), '', '## Fontes', '', citations(s, vault, q.evidence, question_path(q))])
    return wrap(content, incoming, q.id, q.revision)


def render_finding(s, vault, f, incoming=None):
    from app.services import safe
    if f.state == 'superseded':
        alias = s.get(Artifact, 'finding-alias:' + f.id)
        canonical = s.get(Finding, alias.value['canonical_id']) if alias else None
        content = '# Registro reunido\n\nEsta proposta repetia um conhecimento já registrado.\n\n'
        if canonical:
            content += f'[Abrir o registro atual]({vault.permalink(finding_path(canonical))})\n\n'
        content += '## Proposta anterior\n\n' + safe(f.text)
        return wrap(content, incoming, f.id, f.revision)
    content = '\n'.join([
        '# ' + safe(f.text), '', '**Estado:** ' + STATES.get(f.state, f.state), '',
        safe(f.reason), '', '## Fontes', '', citations(s, vault, f.evidence, finding_path(f)), '',
        '## Revisão', '', tick('approve' if f.kind == 'decision' else 'accept', f.state == 'accepted'),
        tick('reject', f.state == 'rejected')])
    return wrap(content, incoming, f.id, f.revision)


def render_index(s, vault, incoming=None):
    from app.services import safe
    from app.references import wiki
    lines = ['# Xereta', '', 'Use o Xereta para responder e revisar. Cada item também tem sua própria nota.', '',
             '## Perguntas', '']
    for q in s.exec(select(Question).where(Question.state.notin_(['withdrawn', 'queued'])).order_by(Question.updated_at.desc())):
        lines.append('- '+wiki(question_path(q),q.text,REVIEW_INDEX)+' — '+STATES.get(q.state,q.state))
    lines += ['', '## Conhecimento e decisões', '']
    for f in s.exec(select(Finding).where(Finding.state != 'superseded').order_by(Finding.created_at.desc())):
        lines.append('- '+wiki(finding_path(f),f.text,REVIEW_INDEX)+' — '+STATES.get(f.state,f.state))
    if getattr(getattr(vault,'settings',None),'library_enabled',False):
        lines += ['', '## Biblioteca', '', '- '+wiki('space/_AgentKnowledge/Referências/index.md','Referências e conexões',REVIEW_INDEX)]
    return wrap('\n'.join(lines), incoming)


def page_record(s, kind, item=None):
    path = question_path(item) if kind == 'question' else finding_path(item) if kind == 'finding' else REVIEW_INDEX
    page = s.get(ReviewPage, path)
    if not page:
        page = ReviewPage(path=path, kind=kind, entity_id=item.id if item else 'index')
        s.add(page)
        s.commit()
    return page


def capture_page(s, vault, page):
    try:
        incoming = vault.capture(page.path)
    except DomainError as error:
        # A crash can leave a first publication journaled before its PUT. There
        # is no confirmed file to protect; creation still uses If-None-Match: *.
        # A previously published file that disappears is held for reconciliation.
        if error.code == 'vault_file_missing' and not page.body:
            return None
        raise
    if page.pending_body and incoming.body == page.pending_body:
        page.body, page.etag, page.pending_body = incoming.body, incoming.etag, ''
        page.state, page.error, page.published_at = 'published', '', now()
        s.add(page)
        s.commit()
    if not page.body:
        raise DomainError('existing_review_page_requires_adoption')
    if mask(section(incoming.body)) != mask(section(page.body)):
        raise DomainError('review_context_edited')
    return incoming


def consume_page(s, page, incoming):
    from app.services import answer_question, review_finding
    if not incoming or page.kind == 'index':
        return
    if page.kind == 'question':
        before = (answer(page.body), *(checkbox(page.body, key) for key in ('confirm', 'decision', 'defer')))
        after = (answer(incoming.body), *(checkbox(incoming.body, key) for key in ('confirm', 'decision', 'defer')))
        if before == after:
            return
        text, confirmed, decision, deferred = after
        if (decision and not confirmed) or (deferred and (confirmed or decision)):
            raise DomainError('incompatible_review_checkboxes')
        qid, revision = page.entity_id, revision_of(page.body, 'question')
        disposition = 'deferred' if deferred else 'decision-approved' if decision else 'confirmed' if confirmed else 'tentative'
        answer_question(s, qid, text, disposition, int(revision), 'vault')
    else:
        f = s.get(Finding, page.entity_id)
        if f.state == 'superseded':
            return
        key = 'approve' if f.kind == 'decision' else 'accept'
        before = checkbox(page.body, key), checkbox(page.body, 'reject')
        after = checkbox(incoming.body, key), checkbox(incoming.body, 'reject')
        if before == after:
            return
        if after[0] == after[1]:
            raise DomainError('incompatible_review_checkboxes')
        revision = revision_of(page.body, 'finding')
        review_finding(s, f.id, 'accepted' if after[0] else 'rejected', int(revision), 'vault')


def migrate_legacy(s, settings, vault):
    from app.services import consume_feedback, save_private
    if s.get(Artifact, 'review:layout-v2'):
        return
    pub = s.get(Publication, 1)
    result = {'legacy': 'none', 'legacy_path': INBOX}
    if pub.body:
        incoming = vault.capture(INBOX)
        save_private(settings.state_path / 'legacy-review' / (digest(incoming.body) + '.md'), incoming.body)
        result = {'legacy': 'archived', 'legacy_path': INBOX, 'sha256': incoming.hash}
        try:
            consume_feedback(s, vault)
        except DomainError as error:
            # The old file and private snapshot stay intact, including unparsed edits.
            result['legacy'], result['error'] = 'needs-review', error.code
    s.add(Artifact(key='review:layout-v2', value=result))
    s.commit()


def consume_review(s, vault):
    for page in s.exec(select(ReviewPage)).all():
        try:
            incoming = capture_page(s, vault, page)
            consume_page(s, page, incoming)
        except DomainError as error:
            page.state, page.error = 'conflict', error.code
            s.add(page)
            s.commit()


def publish_review(s, settings, vault):
    pub = s.get(Publication, 1)
    if not settings.publish_enabled:
        pub.state, pub.error = 'disabled', 'publication_gate_pending'
        s.add(pub); s.commit()
        return
    migrate_legacy(s, settings, vault)
    starting_outbox = s.get(Artifact, 'review:outbox')
    generation = starting_outbox.value.get('generation') if starting_outbox else None
    entities = [('question', q) for q in s.exec(select(Question).where(Question.state.notin_(['withdrawn', 'queued'])))]
    entities += [('finding', f) for f in s.exec(select(Finding))]
    entities += [('index', None)]
    errors = []
    for kind, item in entities:
        page = page_record(s, kind, item)
        try:
            incoming = capture_page(s, vault, page)
            consume_page(s, page, incoming)
            render = render_question if kind == 'question' else render_finding if kind == 'finding' else render_index
            body = render(s, vault, item, incoming) if item else render(s, vault, incoming)
            if not incoming or incoming.body != body:
                page.pending_body, page.state = body, 'submitting'
                s.add(page); s.commit()
                incoming = vault.write_review(page.path, body, incoming.etag if incoming else None)
            page.body, page.etag, page.pending_body = incoming.body, incoming.etag, ''
            page.state, page.error, page.published_at = 'published', '', now()
            s.add(page); s.commit()
        except DomainError as error:
            page.state, page.error = 'conflict', error.code
            errors.append(page.path)
            s.add(page); s.commit()
    pub.state, pub.error = ('partial', 'review_page_conflicts') if errors else ('published', '')
    pub.published_at = now()
    s.add(pub)
    outbox = s.get(Artifact, 'review:outbox')
    if outbox:
        s.refresh(outbox)
        state = 'pending' if outbox.value.get('generation') != generation else 'blocked' if errors else 'complete'
        outbox.value = {**outbox.value, 'state': state}
        s.add(outbox)
    s.commit()
    return {'published': len(entities) - len(errors), 'conflicts': len(errors)}
