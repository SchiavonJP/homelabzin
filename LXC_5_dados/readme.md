# LXC 5 — Dados

Postgres · Redis · FalkorDB

**Criar o LXC no Proxmox**

Na interface web do Proxmox, clica em **Create CT** e preenche assim:

```
Hostname:   sb-dados
Password:   (define uma senha root)
Template:   debian-12 (a que já baixaste)

CPU:        2 cores
RAM:        2048 MB  (2GB — suficiente para Postgres + Redis + FalkorDB)
Swap:       512 MB
Disk:       20 GB    (em qualquer storage que tenhas disponível)

Network:    vmbr0, DHCP  (ou IP fixo se preferires)
DNS:        deixa herdar do host

Name: eth0
Bridge: vmbr0
IPv4: Static
IPv4/CIDR: 192.168.0.210/24
Gateway: 192.168.0.1
```

Na aba **Options** após criar, edita o arquivo de config para habilitar Docker:

```bash
# No shell do Proxmox host (não dentro do LXC)
nano /etc/pve/lxc/<ID_DO_LXC>.conf

# Adiciona estas duas linhas no final:
features: keyctl=1,nesting=1
```

## Pré-requisitos no LXC

```bash
# LXC Debian com nesting=1 no Proxmox
# Instalar Docker
curl -fsSL https://get.docker.com | sh
```

## Deploy via Git

```bash
# SSH access (run once from Proxmox host)
pct exec <VMID> -- mkdir -p /root/.ssh
cat ~/.ssh/id_ed25519.pub | pct exec <VMID> -- tee /root/.ssh/authorized_keys
pct exec <VMID> -- chmod 700 /root/.ssh
pct exec <VMID> -- chmod 600 /root/.ssh/authorized_keys

# Clone only this folder (run on LXC 5)
git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/second-brain-automation.git
cd second-brain-automation
git sparse-checkout init --cone
git sparse-checkout set LXC_5_dados
git checkout main
cd LXC_5_dados
```

## Setup inicial

```bash
# 1. Editar as senhas antes de subir
cp .env.example .env
nano .env   # fill in POSTGRES_PASSWORD, REDIS_PASSWORD, FALKORDB_PASSWORD

# 2. Subir os serviços
docker compose up -d

# 3. Verificar saúde dos containers
docker compose ps
```

### Pull updates

```bash
cd ~/second-brain-automation && git pull
cd LXC_5_dados && docker compose up -d
```

## Verificação

```bash
# Postgres
docker exec sb_postgres pg_isready -U secondbrain

# Redis
docker exec sb_redis redis-cli -a <REDIS_PASSWORD> ping

# FalkorDB (browser em http://<IP_LXC5>:3000)
docker exec sb_falkordb redis-cli -p 6379 -a <FALKORDB_PASSWORD> ping
```

## Connection strings para os outros LXCs

```
# Postgres (Hermes)
postgresql://secondbrain:<senha>@<IP_LXC5>:5432/hermes

# Postgres (Odysseus)
postgresql://secondbrain:<senha>@<IP_LXC5>:5432/odysseus

# Redis
redis://:<senha>@<IP_LXC5>:6379

# FalkorDB
redis://:<senha>@<IP_LXC5>:6380
```

## Notas

- Redis e Postgres não expõem portas externamente — apenas na rede Docker interna `sb_data`
- FalkorDB expõe 6380 (graph) e 3000 (browser) apenas em 127.0.0.1 do LXC
- Para acesso externo ao FalkorDB browser, usar SSH tunnel: `ssh -L 3000:localhost:3000 root@<IP_LXC5>`
- FalkorDB só é necessário quando o Graphify começar a ser usado — pode ficar comentado inicialmente

## Monitoramento (Dockhand/Hawser)

Agente Hawser (`sb_hawser`, porta 2376) registrado no Dockhand (LXC 7) —
detecta atualização de imagem disponível (badge, não aplica sozinho). Ver
`HAWSER_TOKEN` no `.env.example`.



