# Ryot — LXC 12 (Personal Hub)

> **Hostname LXC:** personal-hub
> **IP:** 192.168.0.221
> **Porta:** 8000
> **URL pública:** https://ryot.joaopaulo.me

Stack de tracking pessoal (livros, filmes, jogos, fitness). Totalmente
independente do AFFiNE — banco, rede e volumes próprios. Compartilha só o
SO e o Docker do LXC 12 (Personal Hub, junto com o AFFiNE em `../affine/`).

---

## Deploy

Clone completo em `/root` (sem sparse-checkout — mesmo padrão usado no PNCP):

```bash
cd /root
git clone https://github.com/SchiavonJP/second-brain-automation.git
cd second-brain-automation/LXC_12_personal_hub/ryot

cp .env.example .env
nano .env   # preencher POSTGRES_PASSWORD, SERVER_ADMIN_ACCESS_TOKEN e TMDB_ACCESS_TOKEN
            # (GOOGLE_BOOKS_API_KEY e HARDCOVER_API_KEY são opcionais — só livros)

docker compose -f compose.yml up -d
```

### Busca de filmes/séries não funciona (TMDB/TVDB)

O Ryot **não** vem com chave própria de fábrica — sem `TMDB_ACCESS_TOKEN` configurado,
toda busca falha com um erro genérico ("Failed to search metadata" na UI; nos logs,
`missing field 'page'`/`missing field 'data'`, que é o Ryot tentando decodificar uma
resposta de erro 401 do provedor como se fosse sucesso). Gerar o token em
[themoviedb.org](https://themoviedb.org) → `Settings → API → Request an API Key
(Developer)` → copiar o **"API Read Access Token"** (não a "API Key (v3 auth)" curta)
e colocar em `TMDB_ACCESS_TOKEN` no `.env`. TVDB é opcional (`MOVIES_AND_SHOWS_TVDB_API_KEY`,
cadastro mais burocrático na API v4 deles) — TMDB já cobre bem filme/série sozinho.

## Verificação

```bash
docker compose ps
curl http://192.168.0.221:8000/health
```

## Traefik

Rota já adicionada em `LXC_1_traefik/dynamic/services.yml`
(`ryot.joaopaulo.me` → `http://192.168.0.221:8000`).

## Backup / Restore

```bash
./scripts/backup.sh /mnt/backups/ryot     # dump do Postgres, retenção 14 dias
./scripts/restore.sh /mnt/backups/ryot/ryot-db-<timestamp>.sql.gz
```

Destino recomendado do backup: NFS do Mini PC (`/storage/backups/ryot`),
nunca o banco ativo em si.

## Atualização

```bash
cd /root/second-brain-automation && git pull
cd LXC_12_personal_hub/ryot && docker compose pull && docker compose up -d
```

Versão pinada: `ghcr.io/ignisda/ryot:v10.5.0` — atualizar o pin manualmente
no `compose.yml` ao subir de versão (nunca usar `:latest`).
