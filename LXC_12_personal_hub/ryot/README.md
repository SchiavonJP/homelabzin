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

```bash
mkdir -p /opt/stacks && cd /opt/stacks
git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/second-brain-automation.git
cd second-brain-automation
git sparse-checkout init --cone
git sparse-checkout set LXC_12_personal_hub
git checkout main
cd LXC_12_personal_hub/ryot

cp .env.example .env
nano .env   # preencher POSTGRES_PASSWORD e SERVER_ADMIN_ACCESS_TOKEN

docker compose -f compose.yml up -d
```

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
cd /opt/stacks/second-brain-automation && git pull
cd LXC_12_personal_hub/ryot && docker compose pull && docker compose up -d
```

Versão pinada: `ghcr.io/ignisda/ryot:v10.5.0` — atualizar o pin manualmente
no `compose.yml` ao subir de versão (nunca usar `:latest`).
