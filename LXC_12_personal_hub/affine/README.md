# AFFiNE — LXC 12 (Personal Hub)

> **Hostname LXC:** personal-hub
> **IP:** 192.168.0.221
> **Porta:** 3010
> **URL pública:** https://affine.joaopaulo.me (atrás de Cloudflare Access)

Base de conhecimento pessoal (Notion/Miro-like). Totalmente independente do
Ryot — banco, redis, rede e volumes próprios. Compartilha só o SO e o Docker
do LXC 12, junto com o Ryot em `../ryot/`.

Segue o `compose.yml` oficial do projeto
(https://github.com/toeverything/AFFiNE/releases/latest/download/docker-compose.yml),
com dois desvios documentados:

- `redis:7-alpine` pinado (o oficial usa `redis` sem tag = `latest`).
- `TELEMETRY_ENABLE=false` e `AFFINE_SERVER_HOST`/`AFFINE_SERVER_HTTPS`
  setados para gerar links corretos atrás do Traefik/Cloudflare.

**AFFiNE não tem, até a data de consulta (2026-08-27), um toggle nativo
confirmado para fechar cadastro** ([issue #6141](https://github.com/toeverything/AFFiNE/issues/6141),
sem solução do mantenedor). Mitigado com Cloudflare Access na borda — ver
seção Cloudflare.

---

## Deploy

Clone completo em `/root` (sem sparse-checkout — mesmo padrão usado no PNCP):

```bash
cd /root
git clone https://github.com/SchiavonJP/second-brain-automation.git
cd second-brain-automation/LXC_12_personal_hub/affine

cp .env.example .env
nano .env   # preencher POSTGRES_PASSWORD
mkdir -p data/storage data/postgres config

docker compose -f compose.yml up -d
```

## Verificação

```bash
docker compose ps
curl http://192.168.0.221:3010/api/health
```

## Traefik

Rota já adicionada em `LXC_1_traefik/dynamic/services.yml`
(`affine.joaopaulo.me` → `http://192.168.0.221:3010`).

## Cloudflare Access

Zero Trust → Access → Applications → criar app para `affine.joaopaulo.me`
com policy restringindo ao seu email — mesmo padrão usado em
`windmill.joaopaulo.me`.

## Backup / Restore

```bash
./scripts/backup.sh /mnt/backups/affine     # dump do Postgres + storage + config, retenção 14 dias
./scripts/restore.sh <timestamp> /mnt/backups/affine
```

Destino recomendado: NFS do Mini PC (`/storage/backups/affine`).

## Atualização

```bash
cd /root/second-brain-automation && git pull
cd LXC_12_personal_hub/affine && docker compose pull && docker compose up -d
```

Versão pinada: `ghcr.io/toeverything/affine:stable` (tag oficial de
produção, distinta de `latest`/`nightly`/`canary` — ainda assim é uma tag
móvel; registrar o digest da imagem no deploy pra rollback determinístico:
`docker inspect --format='{{.RepoDigests}}' affine_server`).
