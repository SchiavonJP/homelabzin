# Second Brain — Implementation Plan

> Context document for Claude Code.
> Describes the goal, architecture, decisions made, current state, and next steps.

**Repo:** `https://github.com/SchiavonJP/second-brain-automation.git`

### SSH key setup for LXCs (run from Proxmox host)

```bash
pct exec <VMID> -- mkdir -p /root/.ssh
cat ~/.ssh/id_ed25519.pub | pct exec <VMID> -- tee /root/.ssh/authorized_keys
pct exec <VMID> -- chmod 700 /root/.ssh
pct exec <VMID> -- chmod 600 /root/.ssh/authorized_keys
```

### Deploy any LXC via sparse checkout

```bash
git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/second-brain-automation.git
cd second-brain-automation
git sparse-checkout init --cone
git sparse-checkout set <LXC_folder>   # e.g. LXC_1_traefik
git checkout main
```

---

## Goal

Build a **central knowledge station** self-maintained by LLMs, hosted on a personal Proxmox server. The system must:

- Process, synthesize, and maintain an Obsidian vault automatically via LLM agents
- Be accessible from any machine (home, work) via browser and the Obsidian app
- Run continuous synthesis pipelines (event-driven) and nightly ones (batch)
- Expose centralized skills and persistent memory to any connected agent
- Use local inference (Mac M1 via Ollama) for lightweight tasks and OpenRouter (free models) for heavy tasks
- Be local-first with minimal cloud dependency

The development environment (LXC 6) is secondary — the core is the second brain.

---

## Hardware

| Machine | Specs | Role |
|---------|-------|------|
| Proxmox host | Ryzen 5700G · 64 GB RAM | Main server — runs all LXCs |
| Mac M1 | 16 GB RAM · Ollama | Local inference — lightweight models |
| Mini PC | — | Obsidian Livesync — vault sync (already in production, do not touch) |
| Notebook | Discrete GPU | Reserved for future use |

---

## Architecture — Final Stack

```
Internet / LAN
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  Proxmox Host · Dockhand (LXC management)          │
│                                                     │
│  LXC 1 — sb-traefik   192.168.0.212                │
│    Traefik v3.6 · reverse proxy · Cloudflare TLS   │
│                                                     │
│  LXC 2 — sb-hermes    192.168.0.213                │
│    Hermes (Nous Research) · second brain engine    │
│    MCP server (FastAPI + fastapi_mcp)              │
│                                                     │
│  LXC 3 — sb-odysseus  192.168.0.214                │
│    Odysseus · second brain web interface           │
│                                                     │
│  LXC 4 — sb-router    192.168.0.211                │
│    LiteLLM · AI router · OpenAI-compat endpoint    │
│                                                     │
│  LXC 5 — sb-dados     192.168.0.210                │
│    Postgres · Redis · FalkorDB                     │
│                                                     │
│  LXC 6 — sb-dev       192.168.0.215                │
│    Clean Debian · Remote SSH · CLI tools           │
│                                                     │
│  LXC 7 — sb-monitor   192.168.0.216                │
│    Uptime Kuma · HTTP/TCP/SSL monitoring           │
│    Dockhand · Docker container management UI       │
└─────────────────────────────────────────────────────┘
      │                          │
      ▼                          ▼
Mac M1 (Ollama)          Mini PC (Livesync)
local inference          vault sync
```

---

## Architecture Decisions

### Infrastructure
- **LXC over VM** — no double-kernel overhead; Docker runs with `features: keyctl=1,nesting=1`
- **Dockhand** — LXC management at the Proxmox host level (not inside containers)
- **Traefik v3.6** — reverse proxy with TLS via Cloudflare DNS Challenge (not TLS challenge — ports closed)
- **Cloudflare DNS Challenge** — domain on Cloudflare, API token with `Zone → DNS → Edit` permission
- **Uptime Kuma + Dockhand on LXC 7** — added after a 502 debugging session (Jun 2026) that took 30 min to diagnose manually; Kuma would have surfaced it immediately

### Data
- **Postgres + Redis on dedicated LXC 5** — decoupled from services; each LXC can be restarted independently
- **FalkorDB** instead of Neo4j — lower RAM overhead, Cypher-compatible; enable when Graphify comes in
- **Separate databases** — `hermes` and `odysseus` inside the same Postgres

### AI
- **LiteLLM as central router** — single OpenAI-compatible endpoint; no service knows which backend it's using
- **OpenRouter free models** — DeepSeek R1, DeepSeek V3, Qwen3 Coder, Llama 4 Scout; alias `openrouter/free` as fallback
- **Automatic fallbacks** — Mac M1 offline → OpenRouter automatically
- **Hermes as engine** — nightly pipeline, persistent memory (USER.md, MEMORY.md), auto-generated skills
- **Odysseus as interface** — chat, deep research, vault access via browser from any machine
- **Hermes and Odysseus complementary** — Hermes works in the background; Odysseus consumes the result

### MCP Server
- **FastAPI + fastapi_mcp** — instead of custom protocol code; regular FastAPI endpoints automatically exposed as MCP tools
- **MCP server on LXC 2** — shared between Hermes (producer) and Odysseus (consumer)
- **Vault via SSHFS** — Mini PC mounted on LXC 2 via sshfs; bind volume in compose

### Skills
- **Centralized Git repo** — `agent-skills` on GitHub (private); cloned on LXC 2
- **Served via MCP** — any agent connected to the MCP server accesses the same skills
- **Reference skills** — `obsidian-second-brain` (eugeniughelbur) and `mattpocock/skills` incorporated

---

## LXC Specifications

| LXC | Hostname | IP | CPU | RAM | Disk |
|-----|----------|----|-----|-----|------|
| LXC 1 | sb-traefik | 192.168.0.212 | 1 core | 512 MB | 5 GB |
| LXC 2 | sb-hermes | 192.168.0.213 | 2 cores | 4 GB | 20 GB |
| LXC 3 | sb-odysseus | 192.168.0.214 | 2 cores | 4 GB | 20 GB |
| LXC 4 | sb-router | 192.168.0.211 | 2 cores | 2 GB | 10 GB |
| LXC 5 | sb-dados | 192.168.0.210 | 2 cores | 2 GB | 20 GB |
| LXC 6 | sb-dev | 192.168.0.215 | 2 cores | 2 GB | 20 GB |
| LXC 7 | sb-monitor | 192.168.0.216 | 1 core | 1 GB | 10 GB |

All: Debian 12 · Docker · `features: keyctl=1,nesting=1` on Proxmox

---

## Subdomains (via Traefik + Cloudflare)

| Subdomain | Service | LXC |
|-----------|---------|-----|
| `traefik.domain.com` | Traefik Dashboard | LXC 1 |
| `litellm.domain.com` | LiteLLM UI | LXC 4 |
| `odysseus.domain.com` | Odysseus | LXC 3 |
| `hermes.domain.com` | Hermes dashboard | LXC 2 |
| `monitor.domain.com` | Uptime Kuma | LXC 7 |
| `dockhand.domain.com` | Dockhand | LXC 7 |

---

## Current State by LXC

### ✅ LXC 5 — Data (COMPLETE)
- Postgres 17-alpine with `hermes`, `odysseus`, `secondbrain` databases
- Redis 7-alpine with AOF persistence
- FalkorDB (commentable — enable with Graphify)
- Files: `docker-compose.yml`, `.env`, `init/01_databases.sql`

### ✅ LXC 4 — AI Router (COMPLETE)
- LiteLLM `main-stable` (avoid 1.82.7 and 1.82.8 — security incident)
- Local models: `llama3.1-8b`, `qwen2.5-coder`, `hermes-local` → Mac M1
- Free cloud models: `deepseek-r1`, `deepseek-v3`, `qwen3-coder`, `llama4-scout` → OpenRouter
- Alias `free-auto` → `openrouter/openrouter/free`
- Automatic fallbacks configured
- Cache via Redis on LXC 5
- Files: `docker-compose.yml`, `config.yaml`, `.env`
- **Pending**: replace `<IP_MAC_M1>` with the actual Mac IP; create `litellm` database in Postgres if needed

### ✅ LXC 1 — Infra (COMPLETE)
- Traefik v3.6
- TLS via **Cloudflare DNS Challenge** (not TLS challenge)
  - Requires `CF_DNS_API_TOKEN` with `Zone → DNS → Edit` permission
- Reusable middlewares: `secure-headers`, `rate-limit-api`, `rate-limit-admin`
- File provider with `watch=true` — new routes without restart
- Cloudflare Tunnel (cloudflared) exposing all 4 subdomains — **working**
- Files: `docker-compose.yml`, `.env`, `dynamic/middlewares.yml`, `dynamic/services.yml`, `root/.cloudflared/config.yml`

#### Cloudflared lessons learned
- The systemd service reads `/etc/cloudflared/config.yml` (set via `--config` in ExecStart). **`/root/.cloudflared/config.yml` is ignored by the daemon.**
- For services in other LXCs on the same LAN, cloudflared can route **directly via HTTP** (no Traefik needed). Cloudflare provides HTTPS to the end user.
- `edge-ip-version` must be a **quoted string** `"4"` — integer causes a parse error.
- cloudflared **does not hot-reload** — always `systemctl restart cloudflared` after any config change.
- Each hostname needs a tunnel DNS route: `cloudflared tunnel route dns <tunnel-name> <hostname>`
- QUIC instability causes intermittent 502s. Fix: `systemctl edit cloudflared` and add `Environment="TUNNEL_TRANSPORT_PROTOCOL=http2"` under `[Service]`.

### ✅ LXC 2 — Hermes (COMPLETE)
- Hermes agent running at `https://hermes.joaopaulo.me` (port 9119)
- MCP server (FastAPI + fastapi_mcp) running at `http://192.168.0.213:3100` — **working**
  - 312 skills loaded and served
  - Tools: vault (list, read, write, search, backlinks), skills (list, get, search), memory (user, session, search, synthesis)
  - Bug fixed: missing `import asyncio` in `server.py` — search tools would crash without it
- Vault access deferred — Obsidian syncs via CouchDB at `https://obsidian.joaopaulo.me`; vault endpoints return empty until wired up

### ✅ LXC 3 — Odysseus (COMPLETE)
- Odysseus running at `https://odysseus.joaopaulo.me` (port 7000)
- Deployed from the **official repo's own `docker-compose.yml`** — do not use a custom compose
- Stack includes: Odysseus + ChromaDB + SearXNG + ntfy (all via repo compose)
- Login: `admin` / set via `ODYSSEUS_ADMIN_PASSWORD` in `~/repo/.env`
- `SECURE_COOKIES=true` — local HTTP access (`http://192.168.0.214:7000`) won't work for sessions; always use the HTTPS subdomain
- **Pending**: configure LiteLLM provider and Hermes MCP server in Settings UI

#### Odysseus lessons learned
- Use the repo's own `docker-compose.yml` — custom compose caused psycopg2 errors (unnecessary PostgreSQL override)
- `ODYSSEUS_ADMIN_PASSWORD` only applies on **first boot with a clean database**; changing it later requires wiping data
- Data persists in `root_odysseus_data` Docker named volume (not `./data/` bind mount) — `rm -rf data/` is not enough; use `docker volume rm`
- `docker compose down -v` only removes volumes from the current project — orphan volumes from previous compose runs (different directory) survive
- `SECURE_COOKIES=true` is required for production (Cloudflare HTTPS); local HTTP sessions will be rejected by the browser

### ✅ LXC 7 — Monitor (COMPLETE — pending Proxmox LXC creation)

- Uptime Kuma (`louislam/uptime-kuma:1`) — HTTP/TCP/SSL monitoring for all services
- Dockhand (`fnsys/dockhand:latest`) — Docker container management UI
- Postgres reused from LXC 5 (`dockhand` database)
- Traefik routes: `monitor.joaopaulo.me` (port 3001), `dockhand.joaopaulo.me` (port 3000)
- Files: `docker-compose.yml`, `.env`, `readme`
- **Pending**: create LXC 7 on Proxmox, run `docker exec sb_postgres psql -U secondbrain -c "CREATE DATABASE dockhand;"` on LXC 5, deploy, configure Kuma monitors via UI

### ⏳ LXC 6 — Dev (DEFERRED)
- Clean Debian, no Docker
- Access via VS Code Remote SSH
- Install Node.js, Python, Git, CLI tools
- Low priority — do this after the main stack is stable

---

## Generated Files

```
lxc5-dados/
  docker-compose.yml
  .env
  init/01_databases.sql
  README.md

lxc4-router/
  docker-compose.yml
  config.yaml          ← replace <IP_MAC_M1>
  .env
  README.md

lxc1-infra/
  docker-compose.yml   ← update to Cloudflare DNS Challenge
  .env                 ← add CF_DNS_API_TOKEN
  dynamic/
    middlewares.yml
    services.yml       ← replace LXC IPs
  README.md

lxc2-hermes/
  docker-compose.yml   ← fix :ro on skills; update to mcp-v2
  .env
  mcp-config.json
  mcp-v2/
    server.py          ← FastAPI MCP server (not tested yet)
    pyproject.toml
  README.md

lxc3-odysseus/
  docker-compose.yml   ← replace IPs
  mcp-servers.json     ← replace <IP_LXC2>
  .env
  README.md
```

---

## Next Steps (in order)

### 1. Fix and complete LXC 2 — Hermes

```bash
# Immediate fix in compose — remove :ro from skills
volumes:
  - hermes_data:/opt/data
  - ./skills:/opt/data/skills    # without :ro
  - ./mcp-config.json:/opt/data/mcp-config.json:ro
```

Update `docker-compose.yml` to use MCP server v2 (Python/FastAPI):
- Replace `node:22-alpine` container with `python:3.12-slim`
- Command: `pip install -e . && uvicorn server:app --host 0.0.0.0 --port 3100`
- Volume: `./mcp-v2:/app` instead of `./mcp:/app`

Configure SSHFS for the vault — **not** the Mini PC (it only runs the LiveSync
CouchDB server, no plain-file vault folder exists there). The real target is the
personal Linux notebook, reached via Tailscale (LXC 2 joined the tailnet as a plain
client — see `notebook/readme.md`), mounted with a resilient systemd automount
instead of a one-shot command (the notebook goes on/offline unpredictably):

```bash
apt install -y sshfs
mkdir -p /mnt/obsidian-vault
```

`/etc/fstab`:
```
notebook_user@<IP_TAILSCALE_NOTEBOOK>:/caminho/do/vault /mnt/obsidian-vault fuse.sshfs _netdev,reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,IdentityFile=/root/.ssh/hermes_vault_key,allow_other,x-systemd.automount,x-systemd.idle-timeout=60,noauto 0 0
```

```bash
systemctl daemon-reload
systemctl start mnt-obsidian\x2dvault.automount
```

### 2. Test MCP server v2 and change nomeclature to v1, no need to use v2

```bash
# Health
curl http://192.168.0.213:3100/health

# Swagger UI (automatic FastAPI docs)
http://192.168.0.213:3100/docs

# List notes
curl http://192.168.0.213:3100/vault/notes

# List skills
curl http://192.168.0.213:3100/skills
```

### 3. Complete Traefik — Cloudflare DNS Challenge

Update `docker-compose.yml` on LXC 1:
```yaml
command:
  - --certificatesresolvers.letsencrypt.acme.dnschallenge=true
  - --certificatesresolvers.letsencrypt.acme.dnschallenge.provider=cloudflare
  - --certificatesresolvers.letsencrypt.acme.dnschallenge.resolvers=1.1.1.1:53,8.8.8.8:53
environment:
  CF_DNS_API_TOKEN: ${CF_DNS_API_TOKEN}
```

### 4. Deploy LXC 3 — Odysseus

```bash
mkdir -p /opt/second-brain/odysseus
git clone https://github.com/pewdiepie-archdaemon/odysseus.git repo
# copy compose, .env, mcp-servers.json
docker compose up -d --build
docker compose logs odysseus | grep -i "password"
```

### 5. Deploy LXC 6 — Dev (low priority)

```bash
# Clean Debian, no Docker
apt install -y git curl build-essential
# Node.js via nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
# Python via pyenv or apt
apt install -y python3 python3-pip python3-venv
```

---

## Bonus Steps (optional, low priority)

- **Homepage** (`ghcr.io/gethomepage/homepage:latest`) — static start page with Kuma status badges embedded. Only worth adding if the stack grows beyond ~10 services or accessing from many different machines. Config is a single YAML file — no DB needed. Would live on LXC 7 alongside Kuma + Dockhand, port 3002, route `home.joaopaulo.me`.

---

## Deferred Items (revisit later)

- **Gitea** — mirror GitHub repos for local offline access; useful when agents need frequent access to repos without rate limits
- ~~**Uptime Kuma**~~ — deployed on LXC 7 (`monitor.joaopaulo.me`)
- **FalkorDB activation** — enable when Graphify joins the stack; knowledge graph schema to be defined
- **Graphify** — for code + vault graph; exports to `graph.json` and optionally FalkorDB; run as CLI on LXC 6 or as a Hermes nightly job
- **Hermes nightly pipeline** — configure schedules via `hermes schedule add` once Hermes is stable
- **Vault taxonomy** — Obsidian vault directory structure to be defined (vault is relatively new)
- **Hermes Gateway** — Telegram/Discord for second brain access via mobile

---

## References

- [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) — CLI skill for Obsidian, Claude Code-compatible
- [mattpocock/skills](https://github.com/mattpocock/skills) — engineering skills for agents
- [fastapi_mcp](https://github.com/tadata-org/fastapi_mcp) — exposes FastAPI as an MCP server automatically
- [LiteLLM docs](https://docs.litellm.ai) — model configuration and fallbacks
- [Traefik v3 docs](https://doc.traefik.io/traefik/) — Cloudflare DNS Challenge
- [Hermes — Nous Research](https://nousresearch.com/hermes) — autonomous agent with persistent memory
- [Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) — self-hosted AI workspace