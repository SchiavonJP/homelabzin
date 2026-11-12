import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, ExternalLink, RefreshCw, Search } from 'lucide-react'

type Selection = { paths: string[], revision: number, limit: number }
type Note = { path: string, title: string, size: number, available: boolean, approved: boolean, ingested: boolean, state: string, provider?: string, permalink?: string }
type Catalog = { selection: Selection, notes: Note[] }
type Api = <T>(path: string, body?: unknown, method?: string) => Promise<T>

export function SourcesPanel({ api, notify, running, onDirty }: {
  api: Api, notify: (message: string) => void, running: boolean, onDirty: (dirty: boolean) => void,
}) {
  const client = useQueryClient()
  const result = useQuery({ queryKey: ['source-catalog'], queryFn: () => api<Catalog>('/xereta/source-catalog'), refetchOnWindowFocus: false })
  const [draft, setDraft] = useState<Selection | null>(null)
  const [search, setSearch] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const catalog = result.data, selected = draft ?? catalog?.selection
  const dirty = !!draft && !!catalog && JSON.stringify(draft.paths.slice().sort()) !== JSON.stringify(catalog.selection.paths.slice().sort())
  useEffect(() => { onDirty(dirty); return () => onDirty(false) }, [dirty, onDirty])
  async function save() {
    if (!selected) return
    setBusy(true); setError('')
    try {
      const saved = await api<Selection>('/xereta/source-selection', { paths: selected.paths, expected_revision: selected.revision }, 'PUT')
      client.setQueryData<Catalog>(['source-catalog'], old => old ? { ...old, selection: saved } : old)
      setDraft(null)
      await Promise.all([client.invalidateQueries({ queryKey: ['overview'] }), client.invalidateQueries({ queryKey: ['source-catalog'] })])
      notify('Lote aprovado. Use Digerir agora ou aguarde a próxima revisão noturna.')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return <section className="sources-panel">
    <div className="notice">Escolha de uma a três notas. Salvar autoriza o lote para a digestão manual e noturna; a leitura começa na próxima execução. O lote permanece até você mudar.</div>
    <div className="section-heading"><h2>Notas disponíveis nas fontes</h2><button className="text-button" disabled={busy} onClick={async () => { await result.refetch(); setDraft(null); setError('') }}><RefreshCw size={14}/>Recarregar catálogo e seleção</button></div>
    <p>As memórias e revisões anteriores são preservadas ao trocar o lote. Listar as notas não as envia ao modelo.</p>
    <label className="search"><Search size={16}/><input aria-label="Buscar fontes" placeholder="Buscar por título ou caminho…" value={search} onChange={e => setSearch(e.target.value)}/></label>
    {result.isPending && <p>Carregando catálogo…</p>}
    {result.isError && <p role="alert" className="error">Não foi possível listar o vault. Tente recarregar o catálogo.</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {catalog && selected && <>
      <div className="source-actions"><strong>{selected.paths.length} / 3 selecionadas</strong><button className="primary" disabled={!dirty || busy || running || selected.paths.length < 1} onClick={save}>{busy ? 'Salvando…' : 'Aprovar e salvar lote'}</button></div>
      {running && <p role="status">Há uma digestão em andamento. Aguarde para mudar o lote.</p>}
      {dirty && <p role="status">Seleção ainda não salva. Salve o lote antes de digerir.</p>}
      <div className="selected-sources" aria-label="Lote selecionado"><h3>Lote selecionado</h3>{selected.paths.map(path => <div key={path}><BookOpen size={14}/><span>{path.startsWith('affine:') ? catalog.notes.find(n => n.path === path)?.title || 'Documento AFFiNE' : path}</span><button className="text-button" aria-label={'Remover ' + path} disabled={busy || running} onClick={() => setDraft({ ...selected, paths: selected.paths.filter(p => p !== path) })}>Remover</button></div>)}</div>
      <div className="source-list">{catalog.notes.filter(note => (note.title + ' ' + note.path).toLowerCase().includes(search.toLowerCase())).map(note => {
        const checked = selected.paths.includes(note.path)
        return <article className="source-row" key={note.path}>
          <label><input type="checkbox" aria-label={note.path} checked={checked} disabled={busy || running || (!checked && (!note.available || selected.paths.length >= 3))} onChange={() => setDraft({ ...selected, paths: checked ? selected.paths.filter(p => p !== note.path) : [...selected.paths, note.path] })}/><span><strong>{note.title}</strong><small>{note.provider === 'affine' ? 'AFFiNE · workspace pessoal' : 'SilverBullet · ' + note.path}</small></span></label>
          <div className="source-meta"><span>{!note.available ? 'Indisponível' : note.ingested ? 'Já capturada' : note.approved ? 'Aprovada · ainda não capturada' : 'Nova · não aprovada'}</span><small>{note.available ? note.provider === 'affine' ? 'Conteúdo lido na digestão' : (note.size / 1024).toFixed(1) + ' KB' : ''}</small></div>
          <a aria-label={'Abrir ' + note.title} href={note.permalink || 'https://silverbullet.joaopaulo.me/' + note.path.replace(/\.md$/, '').split('/').map(encodeURIComponent).join('/')} target="_blank" rel="noreferrer"><ExternalLink size={14}/></a>
        </article>
      })}</div>
      <small>Até 24 mil caracteres por nota. Arquivos gerados, de configuração e de conflito ficam fora do processamento.</small>
    </>}
  </section>
}
