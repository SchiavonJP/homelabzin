import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Pause, Play, RefreshCw } from 'lucide-react'
import { requestKey } from './request-key'
import { SourcesPanel } from './sources'
import { ConnectionsPanel } from './connections'
import { LibrarySettings, MigrationPanel } from './library'

type Api = <T>(path: string, body?: unknown, method?: string) => Promise<T>
type Policy = { revision: number, mode: 'manual' | 'automatic', paused: boolean, folders: string[], exclusions: string[], notes_per_day: number, minutes_per_day: number, approved_at: string }
type Status = { next_run_at?: string | null, policy: Policy, budget: { notes_used: number, notes_limit: number, seconds_used: number, seconds_limit: number, seconds_remaining: number, resets_at: string }, progress: Record<string, number>, sections: Record<string, number>, queued_questions: number, proposed_findings: number, last_activity: string, approved_providers?: string[] }
type Preview = { folders: string[], paths: string[], included: number, eligible: number, excluded: number }
type Queue = { notes: { path: string, title?: string, state: string, error: string, next_attempt_at: string, sections_done: number, sections_total: number }[], total: number }
const queueErrors: Record<string, string> = {
  quotation_or_provenance_invalid: 'A proposta do modelo não passou na verificação de citação. A captura foi preservada; nenhuma proposta desse lote foi publicada.',
  invalid_review_schema: 'O modelo retornou um formato inválido. A captura foi preservada para nova tentativa.',
  invalid_review_item: 'Uma proposta não passou na validação. A captura foi preservada.',
  draft_truncated_or_unfinished: 'A resposta do modelo ficou incompleta. O processamento já salvo foi preservado.',
  source_relationship_changed_requires_retain: 'A cópia foi separada e precisa de extração própria. A captura anterior continua preservada.',
  affine_codec_version_mismatch: 'A versão AFFiNE mudou; o leitor precisa ser qualificado antes de continuar.',
  affine_capture_incomplete: 'A nota contém blocos que ainda não podem ser lidos completamente.',
  affine_document_missing: 'Documento indisponível; a captura anterior foi preservada.',
  affine_capture_too_large: 'O documento ultrapassa o limite de captura de 8 MiB.',
  empty_capture: 'A nota está vazia.', capture_too_large: 'A nota ultrapassa o limite de captura de 8 MiB.',
  source_missing_no_automatic_deletion: 'A nota está indisponível; a versão anterior foi preservada.',
  retain_acknowledgement_requires_reconciliation: 'A confirmação da extração precisa ser verificada antes de reenviar.',
  operation_missing_requires_reconciliation: 'A operação remota precisa ser verificada antes de continuar.',
  consolidation_requires_reconciliation: 'A confirmação da consolidação precisa ser verificada.',
  remote_document_mismatch: 'A versão remota não corresponde à seção capturada.',
  remote_operation_failed: 'A extração falhou. Uma nova tentativa será feita após o intervalo indicado.',
}
const labels: Record<string, string> = { unread: 'Não lidas', changed: 'Alteradas', audit: 'Conferindo versão', partial: 'Em processamento', processed: 'Processadas', failed: 'Precisam de atenção', missing: 'Indisponíveis', excluded: 'Excluídas', reviewed: 'Revisadas', retained: 'Memórias extraídas', pending: 'Pendentes', submitted: 'Em extração', held: 'Aguardando reconciliação' }

export function SourcesWorkspace({ api, notify, running, onDirty }: { api: Api, notify: (s: string) => void, running: boolean, onDirty: (v: boolean) => void }) {
  const client = useQueryClient()
  const result = useQuery({ queryKey: ['automation'], queryFn: () => api<Status>('/xereta/automation'), refetchInterval: 5000 })
  const folders = useQuery({ queryKey: ['scope-folders'], queryFn: () => api<Preview>('/xereta/automation/preview', { folders: [], exclusions: [] }, 'POST'), refetchOnWindowFocus: false })
  const [draft, setDraft] = useState<Policy | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [checked, setChecked] = useState<Preview | null>(null), [offset, setOffset] = useState(0)
  const [view,setView]=useState<'integrations'|'processing'>('integrations')
  const [libraryDirty,setLibraryDirty]=useState(false)
  const [batchDirty, setBatchDirty] = useState(false), [connectionDirty, setConnectionDirty] = useState(false)
  const status = result.data, p = draft ?? status?.policy
  const queue = useQuery({ queryKey: ['automatic-queue', offset], queryFn: () => api<Queue>(`/xereta/automation/queue?offset=${offset}&limit=20`), enabled: status?.policy.mode === 'automatic', refetchInterval: 5000 })
  useEffect(() => { onDirty(!!draft || batchDirty || connectionDirty || libraryDirty); return () => onDirty(false) }, [draft, batchDirty, connectionDirty, libraryDirty, onDirty])
  function change(values: Partial<Policy>) { if (p) { setDraft({ ...p, ...values }); setChecked(null) } }
  async function refresh() { await Promise.all([client.invalidateQueries({ queryKey: ['automation'] }), client.invalidateQueries({ queryKey: ['overview'] }), client.invalidateQueries({ queryKey: ['automatic-queue'] })]) }
  async function save() {
    if (!p) return
    setBusy(true); setError('')
    try {
      await api('/xereta/automation', { mode: p.mode, folders: p.folders, exclusions: p.exclusions, notes_per_day: p.notes_per_day, minutes_per_day: p.minutes_per_day, expected_revision: p.revision }, 'PUT')
      setDraft(null); await refresh()
      notify(p.mode === 'automatic' ? 'Escopo aprovado e salvo. Clique em Ativar agora para começar.' : 'Seleção manual ativada. Seu lote anterior foi preservado.')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function control(action: 'pause' | 'resume') {
    if (!status) return
    setBusy(true); setError('')
    try {
      const response = await api<{ state?: string }>(`/xereta/automation/${action}`, { expected_revision: status.policy.revision, ...(action === 'resume' ? { idempotency_key: requestKey('web') } : {}) }, 'POST')
      await refresh()
      notify(action === 'pause' ? 'Pausa solicitada. A etapa atual será salva antes de parar.' : response.state === 'waiting_budget' ? 'Modo automático retomado. O processamento aguarda a renovação do orçamento diário.' : 'Processamento retomado agora. Depois, o Xereta segue o horário da Agenda.')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  if (result.isPending) return <p>Carregando modos de processamento…</p>
  if (!status || !p) return <div role="alert" className="error">Não foi possível carregar a automação. <button onClick={() => result.refetch()}>Tentar novamente</button></div>
  return <>
    <nav className="view-tabs" aria-label="Configuração de fontes"><button aria-pressed={view==='integrations'} onClick={()=>setView('integrations')}>Integrações</button><button aria-pressed={view==='processing'} onClick={()=>setView('processing')}>Processamento</button></nav>
    {(!!draft || batchDirty || connectionDirty || libraryDirty) && <p role="status">Há configurações ainda não salvas. Salve ou descarte o rascunho antes de digerir.</p>}
    <div hidden={view!=='integrations'}>
    <ConnectionsPanel api={api} notify={notify} running={running} onDirty={setConnectionDirty} onSilverbullet={()=>setView('processing')}/>
    <LibrarySettings api={api} notify={notify} onDirty={setLibraryDirty}/>
    <MigrationPanel api={api} notify={notify}/>
    </div><div hidden={view!=='processing'}>
    <section className="automation-panel" id="processing">
      <div className="section-heading"><h2>Como o Xereta escolhe as notas</h2><span>{status.policy.mode === 'automatic' ? status.policy.paused ? 'PAUSADO' : 'AUTOMÁTICO' : 'LOTE MANUAL'}</span></div>
      <p>Aprove pastas uma vez. Novas notas nessas pastas também entram na fila. Seus arquivos originais continuam intactos.</p>
      <label>Modo de seleção<select aria-label="Modo de seleção" value={p.mode} disabled={busy || running} onChange={e => change({ mode: e.target.value as Policy['mode'] })}><option value="manual">Selecionar um lote manualmente</option><option value="automatic">Processar pastas automaticamente</option></select></label>
      {p.mode === 'automatic' && <>
        <fieldset disabled={busy || running}><legend>Pastas aprovadas, incluindo subpastas</legend>
          {folders.isError && <p className="error">Não foi possível listar as pastas. <button onClick={() => folders.refetch()}>Tentar novamente</button></p>}
          <div className="folder-list">{folders.data?.folders.map(folder => <label key={folder}><input type="checkbox" checked={p.folders.includes(folder)} onChange={e => change({ folders: e.target.checked ? [...p.folders, folder] : p.folders.filter(x => x !== folder) })}/>{folder}</label>)}</div>
        </fieldset>
        <label>Excluir arquivos ou pastas<textarea aria-label="Exclusões" rows={3} disabled={busy || running} value={p.exclusions.join('\n')} placeholder={'space/pasta-privada/\nspace/Nota privada.md'} onChange={e => change({ exclusions: e.target.value.split('\n') })} onBlur={() => change({ exclusions: p.exclusions.map(x => x.trim()).filter(Boolean) })}/><small>Um caminho por linha. Termine pastas com /. Arquivos gerados e de configuração são sempre excluídos.</small></label>
        <div className="automation-limits"><label>Notas por dia<input aria-label="Notas por dia" type="number" min={1} max={10} value={p.notes_per_day} disabled={busy || running} onChange={e => change({ notes_per_day: Number(e.target.value) })}/></label><label>Minutos por dia<input aria-label="Minutos por dia" type="number" min={1} max={20} value={p.minutes_per_day} disabled={busy || running} onChange={e => change({ minutes_per_day: Number(e.target.value) })}/></label></div>
        <p>Até três seções por etapa. Notas longas são divididas automaticamente. O limite diário também vale para Digerir agora e Retomar.</p>
        <button className="secondary" disabled={busy || !p.folders.length || p.exclusions.some(x => !x.trim())} onClick={async () => { setBusy(true); setError(''); try { setChecked(await api<Preview>('/xereta/automation/preview', { folders: p.folders, exclusions: p.exclusions }, 'POST')) } catch (e) { setError((e as Error).message) } finally { setBusy(false) } }}>Conferir escopo</button>
        {checked && <div className="notice" role="status">{checked.included} {checked.included === 1 ? 'nota incluída' : 'notas incluídas'} · {checked.excluded} fora do escopo. Esta conferência lê apenas a lista de arquivos.</div>}
      </>}
      {error && <p role="alert" className="error">{error}</p>}
      {draft && <p role="status">Configuração ainda não salva. Suas alterações são preservadas em caso de conflito.</p>}
      <div className="question-actions"><button className="primary" disabled={busy || running || !draft || (p.mode === 'automatic' && !p.folders.length && !status.approved_providers?.length)} onClick={save}>Aprovar e salvar configuração</button>{draft && <button className="text-button" disabled={busy} onClick={async () => { await result.refetch(); setDraft(null); setChecked(null); setError('') }}>Descartar alterações e recarregar</button>}</div>
      {running && <p>Aguarde a execução terminar ou pause o modo automático para alterar a configuração.</p>}
      {status.policy.mode === 'automatic' && <>
        <div className="automation-progress"><h3>Progresso do escopo aprovado</h3><div className="progress-counts">{Object.entries(status.progress).map(([state, count]) => <span key={state}><strong>{count}</strong> {labels[state] || state}</span>)}</div><p>{status.budget.notes_used} / {status.budget.notes_limit} versões de notas iniciadas hoje · {(status.budget.seconds_used / 60).toFixed(1)} / {status.budget.seconds_limit / 60} minutos utilizados.</p><p>{status.queued_questions} perguntas na fila · {status.proposed_findings} achados para revisar. As respostas pendentes não interrompem a leitura.</p><p>Última atividade: {status.last_activity ? new Date(status.last_activity).toLocaleString('pt-BR') : 'Aguardando a primeira execução'} · Próxima revisão: {status.policy.paused ? 'modo pausado' : status.next_run_at ? new Date(status.next_run_at).toLocaleString('pt-BR') : 'Agenda desativada'}.</p><small>Uma nota fica processada quando todas as seções terminam a extração e a preparação da revisão. A confirmação humana é separada. Orçamento renova em {new Date(status.budget.resets_at).toLocaleString('pt-BR')}.</small></div>
        <div className="question-actions">{status.policy.paused ? <button className="primary" disabled={busy || running || !!draft} onClick={() => control('resume')}><Play size={15}/>{status.last_activity ? 'Retomar agora' : 'Ativar agora'}</button> : <button className="secondary" disabled={busy} onClick={() => control('pause')}><Pause size={15}/>Pausar automático</button>}<button className="text-button" onClick={() => refresh()}><RefreshCw size={14}/>Atualizar progresso</button></div>
        {!!queue.data?.notes.length && <div className="automatic-queue"><h3>Fila e exceções</h3>{queue.data.notes.map(note => <article key={note.path}><strong>{note.title || note.path}</strong><span>{labels[note.state] || note.state}{note.sections_total > 0 ? ` · ${note.sections_done}/${note.sections_total} seções` : ''}</span>{note.error && <small>{queueErrors[note.error] || note.error.replaceAll('_', ' ')}{note.next_attempt_at ? ' · nova tentativa: ' + new Date(note.next_attempt_at).toLocaleString('pt-BR') : ''}</small>}</article>)}<div className="question-actions"><button className="secondary small" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>Anteriores</button><span>{offset + 1}–{Math.min(offset + 20, queue.data.total)} de {queue.data.total}</span><button className="secondary small" disabled={offset + 20 >= queue.data.total} onClick={() => setOffset(offset + 20)}>Próximas</button></div></div>}
      </>}
    </section>
    {status.policy.mode === 'manual' && <SourcesPanel api={api} notify={notify} running={running} onDirty={setBatchDirty}/>}
    </div>
  </>
}
