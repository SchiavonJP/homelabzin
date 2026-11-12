import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Pause, Play, RefreshCw } from 'lucide-react'

type Api = <T>(path: string, body?: unknown, method?: string) => Promise<T>
type Scope = { workspace: string, exclusions: string[], approved_at: string, paused: boolean, revision: number }
type Connection = { id: string, provider: string, configured: boolean, workspaces: string[], scope: Scope, health: { state: string, error?: string, last_success_at?: string }, progress: Record<string, number> }
type Relationship = { id: string, source_title: string, target_title: string, state: string, method: string, revision: number, diverged: boolean, source_provider?: string, target_provider?: string, source_url?: string, target_url?: string }
type Data = { connections: Connection[], relationships: Relationship[] }
type Preview = { notes: { path: string, title: string, permalink?: string }[], included: number, excluded: number }
const progressNames: Record<string, string> = { unread: 'não lidas', changed: 'alteradas', partial: 'em processamento', processed: 'processadas', failed: 'precisam de atenção', missing: 'indisponíveis', excluded: 'fora do escopo' }
const healthErrors: Record<string, string> = { affine_codec_version_mismatch: 'A versão AFFiNE mudou. O leitor precisa ser qualificado.', affine_reauth_required: 'Renove a sessão do leitor no servidor.', affine_reader_unavailable: 'Não foi possível acessar o leitor.' }
const healthNames: Record<string, string> = { healthy: 'Conexão verificada', unavailable: 'Indisponível · versões preservadas', reauth_required: 'Reconectar AFFiNE no servidor', unchecked: 'Ainda não verificada' }

export function ConnectionsPanel({ api, notify, running, onDirty, onSilverbullet }: { onSilverbullet?: () => void, api: Api, notify: (message: string) => void, running: boolean, onDirty: (dirty: boolean) => void }) {
  const client = useQueryClient()
  const result = useQuery({ queryKey: ['connections'], queryFn: () => api<Data>('/xereta/connections'), refetchInterval: 10000 })
  const connection = result.data?.connections.find(x => x.id === 'affine')
  const [draft, setDraft] = useState<Scope | null>(null), [preview, setPreview] = useState<Preview | null>(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [search, setSearch] = useState('')
  const scope = draft ?? connection?.scope
  useEffect(() => { onDirty(!!draft); return () => onDirty(false) }, [draft, onDirty])
  async function refresh() { await Promise.all(['connections', 'automation', 'overview', 'automatic-queue', 'source-catalog'].map(key => client.invalidateQueries({ queryKey: [key] }))) }
  async function action(fn: () => Promise<unknown>, message?: string) {
    setBusy(true); setError('')
    try { await fn(); await refresh(); if (message) notify(message) } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  function change(values: Partial<Scope>) { if (scope) setDraft({ ...scope, ...values }) }
  return <section className="sources-panel connections-panel">
    <div className="section-heading"><h2>Conexões de conhecimento</h2><span>UM ORÇAMENTO COMPARTILHADO</span></div>
    <p>SilverBullet e AFFiNE usam a mesma fila, revisão e Agenda. Uma conexão indisponível preserva as capturas e não interrompe a outra.</p>
    <div className="connection-cards">{result.data?.connections.map(item => <article key={item.id}>
      <h3>{item.provider === 'affine' ? 'AFFiNE' : 'SilverBullet / Obsidian'}</h3>
      <p>{healthNames[item.health.state] ?? item.health.state}</p>{item.health.error && <small>{healthErrors[item.health.error] || item.health.error.replaceAll('_', ' ')}</small>}
      {!!Object.keys(item.progress).length && <p>{Object.entries(item.progress).map(([key, value]) => `${value} ${progressNames[key] || key}`).join(' · ')}</p>}
      <small>{item.health.last_success_at ? `Última verificação: ${new Date(item.health.last_success_at).toLocaleString('pt-BR')}` : 'A próxima leitura atualiza o estado.'}</small>
      <p>{item.provider === 'affine' ? !item.configured ? 'Leitor ainda não configurado no servidor.' : item.scope.approved_at ? item.scope.paused ? 'Escopo automático pausado' : 'Habilitada para a próxima digestão' : 'Workspace ainda não aprovado' : 'Usa o escopo de pastas e os controles gerais de processamento.'}</p>
    {item.provider === 'silverbullet' && onSilverbullet && <button className="text-button" onClick={onSilverbullet}>Configurar pastas e processamento</button>}
    </article>)}</div>
    {result.isError && <p role="alert" className="error">Não foi possível carregar as conexões.</p>}
    {connection?.configured && scope && <details className="integration-config"><summary>Configurar AFFiNE</summary>
      <h3>Configuração AFFiNE</h3>{running && <p role="status">Você pode preparar o escopo. Aguarde a digestão terminar para aprovar alterações.</p>}<h3>Workspace AFFiNE</h3><p>O workspace é lido no modo automático; no modo manual, escolha os documentos do lote. Aprovar o workspace inclui documentos futuros. As notas originais continuam intactas; as revisões aparecem no Xereta e nos arquivos já usados no SilverBullet.</p>
      <label>Workspace<select aria-label="Workspace AFFiNE" disabled={busy} value={scope.workspace} onChange={e => { change({ workspace: e.target.value, exclusions: [] }); setPreview(null) }}>
        <option value="">Selecione o workspace</option>{connection.workspaces.map(id => <option key={id} value={id}>Workspace pessoal · {id.slice(0, 8)}</option>)}
      </select></label>
      <div className="question-actions"><button className="secondary" disabled={busy || !scope.workspace} onClick={() => action(async () => { setPreview(await api<Preview>('/xereta/connections/affine/preview', { workspace: scope.workspace, exclusions: scope.exclusions, expected_revision: scope.revision }, 'POST')) })}>Conferir documentos e exclusões</button>
        <button className="text-button" disabled={busy} onClick={() => action(() => api('/xereta/connections/affine/check', {}, 'POST'), 'Conexão AFFiNE verificada.')}><RefreshCw size={14}/>Verificar conexão</button></div>
      {preview && <div className="affine-document-preview"><p>{preview.notes.filter(n => !scope.exclusions.includes(n.path.split(':').at(-1)!)).length} documentos incluídos. As páginas geradas conhecidas ficam fora da ingestão.</p>
        <label>Buscar documentos<input aria-label="Buscar documentos AFFiNE" value={search} onChange={e => setSearch(e.target.value)}/></label>
        <fieldset disabled={busy}><legend>Excluir documentos deste workspace</legend>{preview.notes.filter(n => (n.title + n.path).toLowerCase().includes(search.toLowerCase())).map(note => {
          const id = note.path.split(':').at(-1)!
          return <label key={note.path}><input type="checkbox" checked={scope.exclusions.includes(id)} onChange={e => change({ exclusions: e.target.checked ? [...scope.exclusions, id] : scope.exclusions.filter(x => x !== id) })}/>{note.title || 'Documento sem título · ' + id.slice(0, 8)}{note.permalink && <a href={note.permalink} target="_blank" rel="noreferrer">Abrir nota</a>}</label>
        })}</fieldset></div>}
      {draft && <p role="status">Configuração ainda não salva. Alterações são preservadas se outra janela modificar o escopo.</p>}
      <div className="question-actions"><button className="primary" disabled={busy || running || !draft || !preview || !scope.workspace} onClick={() => action(async () => { await api('/xereta/connections/affine/scope', { workspace: scope.workspace, exclusions: scope.exclusions, expected_revision: scope.revision }, 'PUT'); setDraft(null) }, 'Workspace aprovado e salvo. A ingestão AFFiNE continua pausada até você ativar.')}>Aprovar e salvar workspace</button>
        {draft && <button className="text-button" disabled={busy} onClick={() => { setDraft(null); setPreview(null); setError('') }}>Descartar alterações</button>}
        {connection.scope.approved_at && <button className="secondary" disabled={busy || !!draft} onClick={() => action(() => api(`/xereta/connections/affine/${connection.scope.paused ? 'resume' : 'pause'}`, { expected_revision: connection.scope.revision }, 'POST'), connection.scope.paused ? 'AFFiNE habilitado. Use Digerir agora ou aguarde a Agenda; os controles gerais também se aplicam.' : 'AFFiNE pausado. A etapa em andamento será preservada.')}>
          {connection.scope.paused ? <Play size={14}/> : <Pause size={14}/>}{connection.scope.paused ? 'Ativar AFFiNE' : 'Pausar AFFiNE'}</button>}
      </div>
      {connection.health.state === 'reauth_required' && <p className="notice">A sessão AFFiNE precisa ser renovada no servidor. Sua senha não é armazenada no Xereta; as últimas versões continuam preservadas.</p>}
    </details>}
    {!!result.data?.relationships.length && <details className="copy-relationships"><summary>Cópias e diferenças entre fontes ({result.data.relationships.length})</summary><p>Cópias vinculadas contam como uma família de fontes. Possíveis cópias também não estabelecem evidência independente até serem separadas. Uma diferença não escolhe automaticamente qual nota está correta.</p>
      <div className="source-list">{result.data.relationships.map(row => <article className="source-row" key={row.id}><div><strong><a href={row.source_url} target="_blank" rel="noreferrer">{row.source_provider === 'affine' ? 'AFFiNE' : 'SilverBullet'}: {row.source_title}</a> ↔ <a href={row.target_url} target="_blank" rel="noreferrer">{row.target_provider === 'affine' ? 'AFFiNE' : 'SilverBullet'}: {row.target_title}</a></strong><small>{row.state === 'linked' ? 'Mesma família' : row.state === 'unlinked' ? 'Mantidas separadas pelo proprietário' : 'Possível cópia · título semelhante'}{row.diverged ? ' · conteúdos diferentes' : ' · conteúdos iguais'}</small></div>
        <button className="secondary small" disabled={busy || running} onClick={() => action(() => api(`/xereta/source-relationships/${row.id}`, { state: row.state === 'linked' ? 'unlinked' : 'linked', expected_revision: row.revision }, 'PATCH'), 'Relação entre as fontes atualizada.')}>{row.state === 'linked' ? 'Desvincular' : 'Vincular cópias'}</button>
    </article>)}</div></details>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>
}
