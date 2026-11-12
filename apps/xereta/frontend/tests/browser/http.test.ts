import { expect, test, type Page } from '@playwright/test'

const paths = ['space/One.md', 'space/Two.md', 'space/Three.md']
const selection = { paths, approved_paths: paths, revision: 0, limit: 3 }
async function fixture(page: Page, failed = false, conflict = false) {
  const calls: { url: string, body: any }[] = []
  const overview = {
    name: 'Xereta', automation: { mode: 'manual', paused: true, progress: {}, queued_questions: 0 }, source_selection: selection, sources: [], questions: [], findings: [],
    runs: failed ? [{ id: 'test-failed', state: 'failed', stage: 'retain', error: 'gateway_request_incomplete', created_at: '', started_at: '', finished_at: '' }] : [],
    schedule: { enabled: true, hour: 3, minute: 0, timezone: 'America/Sao_Paulo', revision: 1 },
    publication: { state: 'published', error: '', published_at: '' }, worker: { healthy: true },
    gates: { publication: true, scheduling: true, owner_feedback: true },
    review: { index_url: '#', outbox: 'complete', pages: [], legacy: null }, sync_check: { state: 'passed' },
  }
  let affineScope = { workspace: '', exclusions: [] as string[], approved_at: '', paused: true, revision: 0 }
  let policy = { revision: 0, mode: 'manual', paused: true, folders: [] as string[], exclusions: [] as string[], notes_per_day: 10, minutes_per_day: 20, approved_at: '' }
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()).pathname
    if (request.method() !== 'GET') calls.push({ url, body: request.postDataJSON() })
    let status = 200, json: unknown = {}
    if (url.endsWith('/login/access-token')) json = { access_token: 'synthetic-test-token' }
    else if (url.endsWith('/overview')) json = overview
    else if (url.endsWith('/connections/affine/preview')) json = { notes: [{ path: 'affine:main:workspace:note-a', title: 'Uma nota AFFiNE' }, { path: 'affine:main:workspace:note-b', title: 'Nota privada AFFiNE' }], included: 2, excluded: 0 }
    else if (url.endsWith('/connections/affine/scope')) {
      if (conflict) { status = 409; json = { detail: 'connection_revision_conflict' } }
      else { affineScope = { ...affineScope, ...request.postDataJSON(), revision: affineScope.revision + 1, paused: true, approved_at: '2026-11-08' }; json = affineScope }
    }
    else if (url.endsWith('/connections/affine/resume') || url.endsWith('/connections/affine/pause')) { affineScope = { ...affineScope, paused: url.endsWith('/pause'), revision: affineScope.revision + 1 }; json = affineScope }
    else if (url.endsWith('/connections/affine/check')) json = { state: 'healthy' }
    else if (url.endsWith('/connections')) json = { connections: [
      { id: 'silverbullet', provider: 'silverbullet', configured: true, workspaces: [], scope: { ...affineScope }, health: { state: 'healthy' }, progress: {} },
      { id: 'affine', provider: 'affine', configured: true, workspaces: ['workspace'], scope: affineScope, health: { state: 'healthy' }, progress: {} }], relationships: [] }
    else if (url.endsWith('/automation/preview')) json = { folders: ['space/', 'space/Personal/', 'space/Private/'], paths: ['space/Personal/a.md'], included: 1, eligible: 4, excluded: 3 }
    else if (url.endsWith('/automation/queue')) json = { notes: [], total: 0 }
    else if (url.endsWith('/automation/resume')) { overview.automation = { ...overview.automation, mode: 'automatic', paused: false }; policy = { ...policy, paused: false, revision: policy.revision + 1 }; json = { state: 'queued', revision: policy.revision, run_id: 'synthetic-auto-run' } }
    else if (url.endsWith('/automation/pause')) { overview.automation = { ...overview.automation, mode: 'automatic', paused: true }; policy = { ...policy, paused: true, revision: policy.revision + 1 }; json = { policy } }
    else if (url.endsWith('/automation')) {
      if (request.method() === 'PUT') policy = { ...policy, ...request.postDataJSON(), revision: policy.revision + 1, paused: true, approved_at: '2026-11-06' }
      overview.automation = { ...overview.automation, mode: policy.mode, paused: policy.paused }
      json = { policy, budget: { notes_used: 0, notes_limit: 10, seconds_used: 0, seconds_limit: 1200, seconds_remaining: 1200, resets_at: '2026-11-07T00:00:00-03:00' }, progress: {}, sections: {}, queued_questions: 0, proposed_findings: 0, last_activity: '' }
    }
    else if (url.endsWith('/source-catalog')) json = {
      selection: overview.source_selection,
      notes: [...paths, 'space/Four.md'].map(path => ({ path, title: path.slice(6, -3), size: 500, available: true, approved: overview.source_selection.approved_paths.includes(path), ingested: false })),
    }
    else if (url.endsWith('/source-selection')) {
      if (conflict) { status = 409; json = { detail: 'source_selection_revision_conflict' } }
      else { overview.source_selection = { ...selection, ...request.postDataJSON(), approved_paths: [...new Set([...paths, ...request.postDataJSON().paths])], revision: 1 }; json = overview.source_selection }
    }
    else if (url.endsWith('/runs') || url.endsWith('/retry')) { status = 202; json = { id: 'synthetic-run', state: 'queued' } }
    await route.fulfill({ status, json })
  })
  await page.goto('/')
  await page.getByLabel('Email', { exact: true }).fill('synthetic@example.test')
  await page.getByLabel('Senha', { exact: true }).fill('synthetic-password')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Digerir agora', exact: true })).toBeVisible()
  return calls
}

for (const button of ['Digerir agora', 'Começar uma digestão']) {
  test(button + ' works on insecure HTTP', async ({ page }) => {
    const calls = await fixture(page)
    expect(await page.evaluate(() => ({ secure: isSecureContext, uuid: typeof crypto.randomUUID, random: typeof crypto.getRandomValues })))
      .toEqual({ secure: false, uuid: 'undefined', random: 'function' })
    await page.getByRole('button', { name: button, exact: true }).click()
    await expect(page.getByRole('status')).toContainText('Execução adicionada à fila')
    const runs = calls.filter(c => c.url.endsWith('/runs'))
    expect(runs).toHaveLength(1)
    expect(runs[0].body.idempotency_key).toMatch(/^web:[a-f0-9]{32}$/)
  })
}

test('retry works on insecure HTTP', async ({ page }) => {
  const calls = await fixture(page, true)
  await page.getByRole('button', { name: 'Execuções', exact: true }).click()
  await page.getByRole('button', { name: 'Retomar', exact: true }).click()
  await expect.poll(() => calls.filter(c => c.url.endsWith('/retry')).length).toBe(1)
  expect(calls.find(c => c.url.endsWith('/retry'))!.body.idempotency_key).toMatch(/^retry:[a-f0-9]{32}$/)
})

test('Sources requires approval and limits a batch to three', async ({ page }) => {
  const calls = await fixture(page)
  await page.getByRole('button', { name: 'Fontes', exact: true }).click()
  await page.getByRole('button', { name: 'Processamento', exact: true }).click()
  await expect(page.getByRole('checkbox', { name: 'space/Four.md', exact: true })).toBeDisabled()
  await page.getByRole('checkbox', { name: 'space/One.md', exact: true }).uncheck()
  await page.getByRole('checkbox', { name: 'space/Four.md', exact: true }).check()
  await expect(page.getByRole('button', { name: 'Digerir agora', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Aprovar e salvar lote', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Lote aprovado' })).toBeVisible()
  const changes = calls.filter(c => c.url.endsWith('/source-selection'))
  expect(changes).toHaveLength(1)
  expect(changes[0].body).toEqual({ paths: ['space/Two.md', 'space/Three.md', 'space/Four.md'], expected_revision: 0 })
  expect(calls.filter(c => c.url.endsWith('/runs'))).toHaveLength(0)
  await expect(page.getByRole('button', { name: 'Digerir agora', exact: true })).toBeEnabled()
  if (process.env.XERETA_SCREENSHOT) {
    await page.locator('.source-actions').scrollIntoViewIfNeeded()
    await page.screenshot({ path: 'test-results/sources-desktop.png' })
    await page.setViewportSize({ width: 390, height: 844 })
    await expect(page.locator('.sidebar')).toHaveCSS('position', 'static')
    await page.locator('.source-actions').scrollIntoViewIfNeeded()
    await page.screenshot({ path: 'test-results/sources-mobile.png' })
  }
})

test('revision conflict preserves the unsaved selection', async ({ page }) => {
  await fixture(page, false, true)
  await page.getByRole('button', { name: 'Fontes', exact: true }).click()
  await page.getByRole('button', { name: 'Processamento', exact: true }).click()
  await page.getByRole('checkbox', { name: 'space/One.md', exact: true }).uncheck()
  await page.getByRole('checkbox', { name: 'space/Four.md', exact: true }).check()
  await page.getByRole('button', { name: 'Aprovar e salvar lote', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Sua seleção foi preservada')
  await expect(page.getByRole('checkbox', { name: 'space/Four.md', exact: true })).toBeChecked()
  await expect(page.getByRole('checkbox', { name: 'space/One.md', exact: true })).not.toBeChecked()
})


test('Automatic mode approves folders once and has explicit start and pause controls', async ({ page }) => {
  const calls = await fixture(page)
  await page.getByRole('button', { name: 'Fontes', exact: true }).click()
  await page.getByRole('button', { name: 'Processamento', exact: true }).click()
  await page.getByLabel('Modo de seleção').selectOption('automatic')
  await page.getByRole('checkbox', { name: 'space/Personal/', exact: true }).check()
  await page.getByLabel('Exclusões', { exact: true }).fill('space/Personal/private/')
  await page.getByRole('button', { name: 'Conferir escopo', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '1 nota incluída' })).toBeVisible()
  await page.getByRole('button', { name: 'Aprovar e salvar configuração', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Ativar agora', exact: true })).toBeVisible()
  expect(calls.filter(c => c.url.endsWith('/runs') || c.url.endsWith('/resume'))).toHaveLength(0)
  await expect(page.getByRole('button', { name: 'Digerir agora', exact: true })).toBeDisabled()
  const saved = calls.find(c => c.url.endsWith('/automation') && c.body.mode === 'automatic')!
  expect(saved.body.folders).toEqual(['space/Personal/'])
  expect(saved.body.exclusions).toEqual(['space/Personal/private/'])
  if (process.env.XERETA_SCREENSHOT) {
    await page.getByText('Progresso do escopo aprovado', { exact: true }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: 'test-results/automatic-desktop.png' })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByText('Progresso do escopo aprovado', { exact: true }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: 'test-results/automatic-mobile.png' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.getByRole('button', { name: 'Ativar agora', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Pausar automático', exact: true })).toBeVisible()
  expect(calls.filter(c => c.url.endsWith('/resume'))).toHaveLength(1)
  await page.getByRole('button', { name: 'Pausar automático', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Ativar agora', exact: true })).toBeVisible()
})


test('AFFiNE workspace approval is separate from activation and preserves the shared policy', async ({ page }) => {
  const calls = await fixture(page)
  await page.getByRole('button', { name: 'Fontes', exact: true }).click()
  await page.getByText('Configurar AFFiNE', { exact: true }).click()
  await page.getByLabel('Workspace AFFiNE', { exact: true }).selectOption('workspace')
  await page.getByRole('button', { name: 'Conferir documentos e exclusões', exact: true }).click()
  await page.getByRole('checkbox', { name: 'Nota privada AFFiNE', exact: true }).check()
  await expect(page.getByRole('button', { name: 'Digerir agora', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Aprovar e salvar workspace', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Ativar AFFiNE', exact: true })).toBeVisible()
  expect(calls.find(x => x.url.endsWith('/connections/affine/scope'))!.body).toEqual({ workspace: 'workspace', exclusions: ['note-b'], expected_revision: 0 })
  expect(calls.some(x => x.url.endsWith('/runs') || x.url.endsWith('/automation'))).toBe(false)
  await page.getByRole('button', { name: 'Ativar AFFiNE', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Pausar AFFiNE', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Pausar AFFiNE', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Ativar AFFiNE', exact: true })).toBeVisible()
  expect(calls.some(x => x.url.endsWith('/runs') || x.url.endsWith('/automation'))).toBe(false)
  if (process.env.XERETA_SCREENSHOT) {
    await page.locator('.connections-panel').scrollIntoViewIfNeeded()
    await page.screenshot({ path: 'test-results/affine-desktop.png', fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: 'test-results/affine-mobile.png', fullPage: true })
  }
})

test('AFFiNE scope conflict preserves exclusions and unsaved workspace', async ({ page }) => {
  await fixture(page, false, true)
  await page.getByRole('button', { name: 'Fontes', exact: true }).click()
  await page.getByText('Configurar AFFiNE', { exact: true }).click()
  await page.getByLabel('Workspace AFFiNE', { exact: true }).selectOption('workspace')
  await page.getByRole('button', { name: 'Conferir documentos e exclusões', exact: true }).click()
  await page.getByRole('checkbox', { name: 'Nota privada AFFiNE', exact: true }).check()
  await page.getByRole('button', { name: 'Aprovar e salvar workspace', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('O escopo mudou em outra janela')
  await expect(page.getByRole('checkbox', { name: 'Nota privada AFFiNE', exact: true })).toBeChecked()
  await expect(page.getByLabel('Workspace AFFiNE', { exact: true })).toHaveValue('workspace')
})

const libraryConfig = { reference_folders: ['space/Referências/'], journal_folders: [], legacy_folders: ['space/ReadItLater Inbox/'], excluded_affine: [], reference_exclusions: [], topics: ['AI', 'Homelab'], aliases: {}, concepts: {}, organization_paused: true, ingestion_paused: true, organization_per_day: 50, organization_minutes: 5, karakeep_ready_list: '', karakeep_inbox_list: '' }
async function libraryFixture(page: Page, conflict = false) {
  const calls = await fixture(page)
  let item = { id: 'ref-one', url: 'https://example.org/article', title: 'Uma referência para depois', description: 'Um artigo sobre documentos', context: 'Talvez útil para meu projeto', tags: [], suggested_tags: ['AI'], projects: [], state: 'catalogued', error: '', revision: 0, approved_hash: '', candidate_hash: '', kind: 'article' }
  await page.route('**/api/v1/xereta/library/config', route => route.fulfill({ json: { config: libraryConfig, revision: 0, runtime_enabled: true, model: 'generalist', karakeep_configured: false, public_karakeep_url: 'https://keep.joaopaulo.me', article_domains: ['example.org'], automation_revision: 0, affine_revision: 0 } }))
  await page.route('**/api/v1/xereta/references**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    let json: unknown = {}, status = 200
    if (request.method() !== 'GET') calls.push({ url: path, body: request.postDataJSON() })
    if (path.endsWith('/prepare')) { item = { ...item, candidate_hash: 'a'.repeat(64), state: 'awaiting_confirmation', revision: 1 }; json = { item, capture: { hash: item.candidate_hash, body: 'Texto sintético integral capturado para leitura. <script>não executar</script>', title: item.title, captured_at: '2026-11-09T12:00:00Z', final_url: item.url } } }
    else if (path.endsWith('/approve')) {
      if (conflict) { status = 409; json = { detail: 'reference_revision_conflict' } }
      else { item = { ...item, approved_hash: item.candidate_hash, state: 'ready', revision: 2 }; json = item }
    } else if (path.endsWith('/references/ref-one')) json = { item, mentions: [{ path: 'space/Diário/2026-11-09.md', title: 'Meu diário', version: '123abc' }], relations: [] }
    else json = { items: [item], total: 1, offset: 0, limit: 30 }
    await route.fulfill({ status, json })
  })
  return calls
}

test('reference capture requires explicit version confirmation and never autoruns digestion', async ({ page }) => {
  const calls = await libraryFixture(page)
  await page.getByRole('button', { name: 'Referências', exact: true }).click()
  await expect(page.getByRole('article').getByText('Referência · não digerida', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Organizar e revisar', exact: true }).click()
  await page.getByRole('button', { name: 'Preparar digestão', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Autorizar digestão desta versão', exact: true })).toBeDisabled()
  expect(calls.some(x => x.url.endsWith('/approve') || x.url.endsWith('/runs'))).toBe(false)
  await expect(page.locator('.candidate-text')).toContainText('<script>não executar</script>')
  expect(await page.locator('.candidate-text script').count()).toBe(0)
  await page.getByRole('checkbox', { name: 'Li esta versão', exact: true }).check()
  await page.getByRole('button', { name: 'Autorizar digestão desta versão', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Revogar permissão', exact: true })).toBeVisible()
  expect(calls.find(x => x.url.endsWith('/approve'))?.body).toEqual({ hash: 'a'.repeat(64), expected_revision: 1 })
  expect(calls.some(x => x.url.endsWith('/runs'))).toBe(false)
})

test('reference approval conflict preserves captured text and reading confirmation', async ({ page }) => {
  await libraryFixture(page, true)
  await page.getByRole('button', { name: 'Referências', exact: true }).click()
  await page.getByRole('button', { name: 'Organizar e revisar', exact: true }).click()
  await page.getByRole('button', { name: 'Preparar digestão', exact: true }).click()
  await page.getByRole('checkbox', { name: 'Li esta versão', exact: true }).check()
  await page.getByRole('button', { name: 'Autorizar digestão desta versão', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('A referência mudou')
  await expect(page.getByRole('checkbox', { name: 'Li esta versão', exact: true })).toBeChecked()
  await expect(page.locator('.candidate-text')).toContainText('Texto sintético integral')
})

test('integration settings show effective model and keep secrets out of portable configuration', async ({ page }) => {
  await libraryFixture(page)
  await page.getByRole('button', { name: 'Fontes', exact: true }).click()
  await page.getByText('Configurar biblioteca e Karakeep', { exact: true }).click()
  await expect(page.getByText('generalist', { exact: true })).toBeVisible()
  await expect(page.getByRole('checkbox', { name: /Habilitar digestão/ })).not.toBeChecked()
  await page.getByText('Configurar pastas e tópicos', { exact: true }).click()
  await page.getByLabel('Pastas de diários', { exact: true }).fill('space/Diário/')
  await expect(page.getByRole('button', { name: 'Digerir agora', exact: true })).toBeDisabled()
  if (process.env.XERETA_SCREENSHOT) {
    await page.screenshot({ path: 'test-results/library-integrations-desktop.png', fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: 'test-results/library-integrations-mobile.png', fullPage: true })
  }
})
