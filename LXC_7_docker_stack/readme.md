# LXC 7 — Monitor Stack

> **Hostname:** sb-monitor  
> **IP:** 192.168.0.216

| Serviço | Porta | Acesso público |
|---------|-------|---------------|
| Uptime Kuma | 3001 | `https://monitor.joaopaulo.me` |
| Dockhand | 3000 | `https://dockhand.joaopaulo.me` |
| Homepage | 3002 | `https://home.joaopaulo.me` |

---

## Specs do LXC

```
CPU:  1 core
RAM:  1 GB
Disk: 10 GB
```

---

## Pré-requisitos

```bash
# LXC Debian 12 — features: keyctl=1,nesting=1 no /etc/pve/lxc/<id>.conf
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
```

### Banco do Dockhand (LXC 5 — uma única vez)

```bash
docker exec -it sb_postgres psql -U secondbrain -c "CREATE DATABASE dockhand;"
```

---

## Deploy

```bash
git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/second-brain-automation.git
cd second-brain-automation
git sparse-checkout init --cone
git sparse-checkout set LXC_7_docker_stack
git checkout main
cd LXC_7_docker_stack

cp .env.example .env
nano .env  # preencher as keys
docker compose up -d
```

---

## Variáveis (.env)

| Variável | Descrição |
|----------|-----------|
| `DOCKHAND_DB_USER` | Usuário Postgres (LXC 5) |
| `DOCKHAND_DB_PASS` | Senha Postgres |
| `PROXMOX_TOKEN_ID` | API token do Proxmox (`homepage@pam!homepage`) |
| `PROXMOX_TOKEN_SECRET` | Secret do token Proxmox |
| `JELLYFIN_API_KEY` | Dashboard → API Keys → + |
| `RADARR_API_KEY` | Radarr → Settings → General → API Key |
| `SONARR_API_KEY` | Sonarr → Settings → General → API Key |
| `LIDARR_API_KEY` | Lidarr → Settings → General → API Key |
| `QBITTORRENT_PASSWORD` | Senha do qBittorrent WebUI |

---

## Homepage

Dashboard centralizado com todos os serviços do homelab. Config em `homepage/`:

| Arquivo | Conteúdo |
|---------|---------|
| `settings.yaml` | Tema, layout dos grupos |
| `services.yaml` | Todos os serviços com ícones, pings e widgets |
| `widgets.yaml` | Widgets globais do topo (data/hora, busca) |
| `docker.yaml` | Auto-discovery (desabilitado) |

**Acesso:** `http://192.168.0.216:3002` · `https://home.joaopaulo.me`

Para adicionar ao Cloudflare Tunnel: Zero Trust → Tunnels → Public Hostnames → Add:
- Subdomain: `home`, Domain: `joaopaulo.me`, Service: `http://192.168.0.216:3002`

---

## Acesso

```
Uptime Kuma  http://192.168.0.216:3001   (ou https://monitor.joaopaulo.me)
Dockhand     http://192.168.0.216:3000   (ou https://dockhand.joaopaulo.me)
Homepage     http://192.168.0.216:3002   (ou https://home.joaopaulo.me)
```

---

## Monitors a configurar no Kuma (após 1º login)

| Tipo  | Alvo | Nome |
|-------|------|------|
| HTTPS | https://hermes.joaopaulo.me | Hermes |
| HTTPS | https://litellm.joaopaulo.me | LiteLLM |
| HTTPS | https://odysseus.joaopaulo.me | Odysseus |
| HTTPS | https://monitor.joaopaulo.me | Kuma (self) |
| HTTPS | https://jellyfin.joaopaulo.me | Jellyfin |
| HTTPS | https://home.joaopaulo.me | Homepage |
| TCP | 192.168.0.213:9119 | Hermes (LAN) |
| TCP | 192.168.0.213:3100 | MCP server |
| TCP | 192.168.0.211:4000 | LiteLLM API |
| TCP | 192.168.0.210:5432 | Postgres |
| TCP | 192.168.0.210:6379 | Redis |
| TCP | 192.168.0.218:8096 | Jellyfin (LAN) |
| TCP | 192.168.0.219:9696 | Prowlarr |
| TCP | 192.168.0.220:8080 | qBittorrent |
| TCP | 192.168.0.12:4533 | Navidrome |

---

## Verificar

```bash
docker ps | grep -E "kuma|dockhand|homepage"
curl -s http://192.168.0.216:3001
curl -s http://192.168.0.216:3002
```
