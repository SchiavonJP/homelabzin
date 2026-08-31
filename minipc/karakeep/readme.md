# Mini PC — Karakeep (guardar links)

> **Acesso:** `http://192.168.0.12:3000`
> **URL pública:** https://keep.joaopaulo.me

Karakeep guarda links (artigos, vídeos, o que for) com metadata, título,
thumbnail, descrição, tags, coleções e notas — **sem baixar o arquivo de
vídeo/áudio em nenhum momento**.

## Vídeo vs. metadata — por que não baixa

O Karakeep usa `yt-dlp` internamente **só se** a variável
`CRAWLER_VIDEO_DOWNLOAD` estiver explicitamente `true`. O default oficial é
`false` (confirmado em docs.karakeep.app/configuration, 2026-08-27) — e esse
`.env.example` **nunca define essa variável**, então o comportamento padrão
prevalece: ao salvar um link do YouTube (ou qualquer vídeo), o Karakeep
guarda só URL, título, thumbnail, descrição e metadados de busca.

Isso é diferente de:
- `CRAWLER_STORE_SCREENSHOT` (default `true`, mantido ligado) — captura uma
  imagem estática da página, não o vídeo.
- `CRAWLER_FULL_PAGE_ARCHIVE` (default `false`, mantido desligado) —
  arquivamento de artigos/páginas completas, não tem relação com vídeo.

**Nunca defina `CRAWLER_VIDEO_DOWNLOAD=true` neste deploy.**

## Componentes

- `web` — app principal (Next.js), SQLite embutido em `/data`
- `chrome` — headless Chrome, usado só para screenshot/archive de página
- `meilisearch` — índice de busca full-text

Sem Postgres — Karakeep usa SQLite embutido, tudo no volume `data`.
Sem IA nesta implantação (sem `OPENAI_API_KEY`/`OLLAMA_BASE_URL`, sem
LiteLLM) — decisão do operador, pode ser habilitado depois.

## Deploy

```bash
mkdir -p /opt/karakeep && cd /opt/karakeep
# copiar docker-compose.yml, .env.example, scripts/ deste diretório do repo

cp .env.example .env
# preencher MEILI_MASTER_KEY e NEXTAUTH_SECRET:
openssl rand -base64 36 | tr -dc 'A-Za-z0-9'

docker compose up -d
```

## Primeiro acesso

1. Acessar `http://192.168.0.12:3000` (ou `https://keep.joaopaulo.me` depois
   do Traefik/Cloudflare configurados)
2. Criar a conta admin
3. **Depois** de criar a conta, editar `.env` e descomentar
   `DISABLE_SIGNUPS=true`, depois `docker compose up -d` de novo — fecha
   cadastro pra qualquer outra pessoa.

## Teste obrigatório — confirmar que vídeo não é baixado

```bash
# Salvar um link de vídeo do YouTube pela UI, depois:
docker exec minipc_karakeep sh -c "find /data -iname '*.mp4' -o -iname '*.webm' -o -iname '*.mkv' -o -iname '*.mp3' -o -iname '*.m4a'"
# Esperado: nenhuma saída (nenhum arquivo de vídeo/áudio no volume)

docker exec minipc_karakeep du -sh /data   # tamanho do volume — deve ser pequeno (KBs/poucos MBs), não GBs
```

## Traefik

Rota em `LXC_1_traefik/dynamic/services.yml` (mesmo Traefik que já roda
neste Mini PC): `keep.joaopaulo.me` → `http://192.168.0.12:3000`.

## Backup / Restore

```bash
./scripts/backup.sh /storage/backups/karakeep   # tar do volume "data", retenção 14 dias
./scripts/restore.sh /storage/backups/karakeep/karakeep-data-<timestamp>.tar.gz
```

`meilisearch` é reconstruível (reindexação automática) — não crítico pro
backup, priorizamos o volume `data`.

## Atualização

Pin de versão via `.env`: `KARAKEEP_VERSION=0.33.2` (nunca usar `latest`).
Atualizar o valor manualmente e rodar `docker compose pull && docker compose up -d`.
