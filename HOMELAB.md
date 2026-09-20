# Homelab — Overview

> Last updated: 2026-09-19

---

## Hardware

| Machine | Specs | Role |
|---------|-------|------|
| **Proxmox host** | Ryzen 5700G · 64 GB RAM · RTX 3060 | Main server — all LXC containers + GPU passthrough |
| **Mini PC** | CasaOS (`192.168.0.12:8888`) | Storage 24/7 + serviços leves (NFS, Navidrome) |
| **Mac M1** | 16 GB RAM · Ollama | Local lightweight inference |

---

## Mini PC — CasaOS (192.168.0.12, sempre ligado)

- **OS:** CasaOS · acesso: `http://192.168.0.12:8888`
- **Papel:** dono do storage e serviços 24/7

### Storage

```
/storage/
├── music/       ← biblioteca musical (Navidrome + Lidarr)
├── movies/      ← filmes (Radarr + Jellyfin)
├── tv/          ← séries (Sonarr + Jellyfin)
└── downloads/   ← landing zone do qBittorrent
```

Exportado via NFS Docker (`erichough/nfs-server`) para toda a rede `192.168.0.0/24`. O setup remove o `nfs-kernel-server` nativo antes de subir o container. Setup: [minipc/nfs/setup-nfs.sh](minipc/nfs/setup-nfs.sh)

### Serviços em execução

| Container | Porta | Role |
|-----------|-------|------|
| `traefik` | 80, 443, 8088 | Reverse proxy local (própria instância no Mini PC) |
| `cloudflared` | — | Cloudflare Tunnel |
| `obsidian-livesync` (CouchDB 3.5) | 5984 | Vault sync — **não tocar** |
| `nextcloud` (big-bear) | 7580 | File cloud / storage pessoal |
| `db-nextcloud` (Postgres 14) | — | Banco do Nextcloud |
| `redis-nextcloud` (Redis 6.2) | — | Cache do Nextcloud |
| `code-server` | 8082 | VS Code no browser |
| `minipc_navidrome` | 4533 | Streaming de música 24/7 |
| `minipc_nfs` (erichough/nfs-server) | 2049, 111 | Exporta `/storage` para os LXCs do Proxmox |
| `immich` | 2283 | Backup de fotos/vídeos — Google Photos (sem ML) |
| `adguard` | 3001, 53 | DNS ad-blocker — rede local + Tailscale |
| `vaultwarden` | — | Gerenciador de senhas (`vault.joaopaulo.me`) |
| `minipc_superproductivity` | 8083 | Gestão de tarefas (`sp.joaopaulo.me`) — sync via Nextcloud WebDAV |
| `syncthing` (CasaOS) | 8384 | Sync de arquivos P2P — relay para Logseq e outros |

Configs: [minipc/nfs/](minipc/nfs/) · [minipc/navidrome/](minipc/navidrome/) · [minipc/super-productivity/](minipc/super-productivity/) · [minipc/logseq/](minipc/logseq/)

---

## Proxmox — LXC Stack (192.168.0.200:8006)

All containers run Debian 12 with Docker, deployed via sparse checkout from the [`second-brain-automation`](https://github.com/SchiavonJP/second-brain-automation) repo.

### Bootstrap padrão de um novo LXC

Sequência completa pra preparar um LXC recém-criado (`pct create` já feito)
antes do deploy da stack em si. Rodar do host Proxmox (`ssh root@192.168.0.200`).
Substituir `<VMIDs>` e `<IPs>` pelos containers reais — pode ser um só ou
vários de uma vez, já que são loops.

```bash
# 1. Senha de root (acesso via console VNC/noVNC do Proxmox — SSH por
#    chave não precisa disso, é só fallback pra quando a chave não rolar)
for ID in <VMIDs>; do
    pct exec $ID -- passwd root
done

# 2. Habilitar Docker (nesting + keyctl) e reiniciar
#    Redundante se o LXC já foi criado com --features keyctl=1,nesting=1
#    no próprio `pct create` (padrão usado nos LXCs mais recentes)
for ID in <VMIDs>; do
    echo "features: keyctl=1,nesting=1" >> /etc/pve/lxc/${ID}.conf
    pct reboot $ID
done

# 3. Injetar chave SSH (acesso sem senha + permite git clone via SSH)
for ID in <VMIDs>; do
    pct exec $ID -- mkdir -p /root/.ssh
    cat ~/.ssh/id_ed25519.pub | pct exec $ID -- tee /root/.ssh/authorized_keys
    cat ~/.ssh/id_ed25519     | pct exec $ID -- tee /root/.ssh/id_ed25519
    pct exec $ID -- chmod 700 /root/.ssh
    pct exec $ID -- chmod 600 /root/.ssh/authorized_keys /root/.ssh/id_ed25519
done

# 4. Instalar Docker (via IP, depois que a chave já está injetada)
for IP in <IPs>; do
    ssh root@$IP "apt-get update -qq && apt-get install -y curl"
done
for IP in <IPs>; do
    ssh root@$IP "curl -fsSL https://get.docker.com | sh"
done
```

> A chave privada copiada no passo 3 precisa estar cadastrada no GitHub
> (Settings → SSH keys) pra o LXC conseguir `git clone` do repo via SSH.
> Depois desse bootstrap, seguir o deploy específico da stack (sparse
> checkout + `docker compose up -d`) documentado no readme de cada LXC.

Pra mudar a senha de root depois (sem repetir o bootstrap todo):
```bash
pct exec <VMID> -- passwd root                                  # interativa
pct exec <VMID> -- bash -c "echo 'root:NOVASENHA' | chpasswd"   # direta
```

### AI / Second Brain (LXCs 1-8)

| LXC | Hostname | Codename | IP | Role |
|-----|----------|----------|----|------|
| 1 | sb-traefik | — | 192.168.0.212 | Reverse proxy + TLS |
| 2 | sb-hermes | **Hermes** | 192.168.0.213 | AI agent engine + MCP server |
| 3 | sb-odysseus | **Odysseus** | 192.168.0.214 | AI workspace (web UI) |
| 4 | sb-router | — | 192.168.0.211 | LLM router (LiteLLM) |
| 5 | sb-dados | **Dados** | 192.168.0.210 | Databases (Postgres + Redis + FalkorDB) |
| 6 | sb-dev | — | 192.168.0.215 | Dev environment (deferred) |
| 7 | sb-monitor | — | 192.168.0.216 | Monitoring + container management |
| 8 | apollo | **Apollo** | 192.168.0.217 | Local GPU inference (RTX 3060) |

### Media Stack (LXCs 9-12, sob demanda)

| LXC | Hostname | IP | Role |
|-----|----------|----|------|
| 9 | sb-media | 192.168.0.218 | Jellyfin (streaming, CPU transcoding) |
| 10 | sb-arr | 192.168.0.219 | Arr stack + Music Auto (Radarr · Sonarr · Lidarr · Prowlarr · Bazarr · slskd · Soularr · Beets) |
| 11 | sb-downloads | 192.168.0.220 | qBittorrent |

### Camera (LXC 13)

| LXC | Hostname | IP | Role |
|-----|----------|----|------|
| 13 | sb-camera | 192.168.0.222 | motionEye — webcam USB, monitoramento do cachorro |

---

### LXC 1 — Traefik (Reverse Proxy)

- **Service:** Traefik v3.6
- **Access:** `192.168.0.212` · `traefik.joaopaulo.me`
- **Ports:** 80, 443
- **Resources:** 1 core · 512 MB RAM · 5 GB disk

TLS via Cloudflare DNS Challenge. Routes all public subdomains. Cloudflare Tunnel (cloudflared) exposes services without open inbound ports. Reusable middlewares: `secure-headers`, `rate-limit-api`, `rate-limit-admin`. File provider with hot-reload (`watch=true`).

> **Status (2026-09-19):** este LXC não está rodando no host no momento —
> não aparece em `pct list`/`qm list` e `192.168.0.212` não responde. Todos
> os subdomínios públicos abaixo ficam inacessíveis até ser restaurado;
> serviços continuam acessíveis via IP local nesse meio tempo.

---

### LXC 2 — Hermes (AI Agent Engine + MCP Server)

- **Services:** Hermes agent · FastAPI MCP server
- **Access:** `192.168.0.213` · `hermes.joaopaulo.me`
- **Ports:** 9119 (Hermes dashboard) · 3100 (MCP SSE)
- **Resources:** 2 cores · 4 GB RAM · 20 GB disk

Core of the second-brain system. Hermes (Nous Research) runs nightly synthesis pipelines, maintains persistent memory (`USER.md`, `MEMORY.md`), and auto-generates skills. The MCP server (FastAPI + `fastapi_mcp`) exposes 312+ skills and vault tools over SSE — any connected agent consumes the same skill catalog. Tools: vault CRUD, full-text search, backlinks, memory synthesis.

---

### LXC 3 — Odysseus (AI Workspace)

- **Service:** Odysseus (self-hosted AI workspace)
- **Access:** `192.168.0.214` · `odysseus.joaopaulo.me`
- **Port:** 7000
- **Resources:** 2 cores · 4 GB RAM · 20 GB disk

Web-based AI workspace for chat, deep research, and vault access from any machine. Includes ChromaDB (vector store), SearXNG (private web search), and ntfy (notifications). Connects to the Hermes MCP server to share skills and memory.

---

### LXC 4 — LiteLLM + Langfuse (AI Router + Observabilidade)

- **Services:** LiteLLM (`main-stable`) · Langfuse 3 (traces + custos) · ClickHouse (storage de eventos)
- **Access:** `192.168.0.211` · `litellm.joaopaulo.me` · `langfuse.joaopaulo.me`
- **Ports:** 4000 (LiteLLM) · 3001 (Langfuse)
- **Resources:** 2 cores · 4 GB RAM · 10 GB disk

Central OpenAI-compatible LLM router. Single endpoint; no service knows which backend it's hitting. Routes to:

| Alias | Backend | Notes |
|-------|---------|-------|
| `local-coder` / `hermes-local` | Apollo (RTX 3060) | Qwen3.6-35B-A3B-MTP |
| `llama3.1-8b` / `qwen2.5-coder` | Mac M1 (Ollama) | Lightweight local |
| `deepseek-r1` / `deepseek-v3` | OpenRouter | Free tier |
| `qwen3-coder` / `llama4-scout` | OpenRouter | Free tier |
| `free-auto` | OpenRouter auto | Best free model available |

Automatic fallback: Mac M1 offline → OpenRouter. Response cache via Redis (LXC 5).

---

### LXC 5 — Dados (Databases)

- **Services:** Postgres 17 · Redis 7 · FalkorDB
- **Access:** `192.168.0.210` (LAN only)
- **Ports:** 5432 (Postgres) · 6379 (Redis) · 6380 (FalkorDB)
- **Resources:** 2 cores · 2 GB RAM · 20 GB disk

Dedicated data layer, decoupled from all services so any container can restart independently. Postgres holds four databases: `hermes`, `odysseus`, `secondbrain`, `dockhand`. Redis uses AOF persistence and serves as LiteLLM response cache. FalkorDB (Cypher-compatible, low-RAM) reserved for the Graphify knowledge graph.

---

### LXC 6 — Dev (Development Environment)

- **Access:** `192.168.0.215` via VS Code Remote SSH
- **Resources:** 2 cores · 2 GB RAM · 20 GB disk
- **Status:** Deferred — deploy after main stack stabilizes

Clean Debian 12, no Docker. Intended for Node.js, Python, and CLI tooling — accessible as a remote dev box from any machine.

---

### LXC 7 — Monitor (Observability + Dashboard)

- **Services:** Uptime Kuma · Dockhand · Homepage
- **Access:** `192.168.0.216` · `monitor.joaopaulo.me` · `dockhand.joaopaulo.me` · `home.joaopaulo.me`
- **Ports:** 3001 (Kuma) · 3000 (Dockhand) · 3002 (Homepage)
- **Resources:** 1 core · 1 GB RAM · 10 GB disk

Uptime Kuma monitors all services via HTTP/TCP/SSL. Dockhand provides a Docker container management UI. Homepage (`ghcr.io/gethomepage/homepage`) is the central dashboard with all homelab services organized in groups, service pings, and *arr widgets. Config in `LXC_7_docker_stack/homepage/`.

---

### LXC 8 — Apollo (GPU Inference)

- **Services:** llama-server (Qwen3.6-35B-A3B-MTP) · bge-embedding (bge-m3)
- **Access:** `192.168.0.217` · `apollo.joaopaulo.me`
- **Ports:** 8080 (inference) · 8081 (embeddings)
- **Resources:** 8 cores · 48 GB RAM · 8 GB swap · 50 GB disk · **RTX 3060 12 GB (passthrough)**

Local GPU inference node. Runs `llama-server` (llama.cpp compiled with CUDA) and a separate `bge-embedding` service. Both are systemd services sourcing their config from `/etc/llama-server.env` and `/etc/bge-embedding.env`. Exposes an OpenAI-compatible API consumed by LiteLLM (`local-coder`/`hermes-local`).

| Service | Model | Port | VRAM | Performance |
|---------|-------|------|------|-------------|
| llama-server | Qwen3.6-35B-A3B-MTP UD-Q4_K_M | 8080 | ~11.1 GB (`--n-cpu-moe 28`, ctx 172032) | ~39 tok/s |
| bge-embedding | bge-m3 Q4_K_M | 8081 | ~570 MB (NGL=99) | 500–1000 emb/s · dim=1024 |

**Offload strategy — `--n-cpu-moe` em vez de `--n-gpu-layers` parcial:** para modelos MoE, offload por layer inteira (`-ngl` parcial) desperdiça VRAM em pesos de experts que raramente são ativados. `--n-cpu-moe N` mantém `-ngl 99` (atenção/norms/embeddings sempre na GPU — pequenos, sempre computados) e manda só os pesos dos experts MoE das primeiras N layers pra CPU RAM (grandes em disco, esparsos por token). Ajustar N incrementalmente: mais alto = mais RAM/menos VRAM/mais contexto cabe; mais baixo = mais VRAM/mais rápido, até faltar memória (erro `cudaMalloc failed: out of memory`, serviço reinicia em loop — se acontecer, baixar N ou o `LLAMA_CTX_SIZE`). MTP nativo (`--spec-type draft-mtp`) foi testado nos dois modelos abaixo e **piorou** a velocidade em ambos — o offload parcial pra CPU já é o gargalo, e o overhead de rascunhar+verificar não compensa nesse hardware.

**Config atual (padrão) — Qwen3.6-35B-A3B-MTP:**
```
LLAMA_MODEL_PATH=/models/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf
LLAMA_CTX_SIZE=172032
LLAMA_NGL=99
LLAMA_THREADS=6
LLAMA_EXTRA_ARGS="--n-cpu-moe 28 --no-mmproj"
```
(`--cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on` fixos em `run-llama-server.sh`)

**Modelos alternativos já baixados em `/models/`** — trocar é só editar `/etc/llama-server.env` e `systemctl restart llama-server`, nenhum download necessário:

| Modelo | `LLAMA_MODEL_PATH` | `LLAMA_EXTRA_ARGS` | Contexto testado | Velocidade |
|---|---|---|---|---|
| **Qwen3.6-35B-A3B-MTP** (padrão) | `/models/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` | `"--n-cpu-moe 28 --no-mmproj"` | 172032 | ~39 tok/s · 73.4% SWE-bench |
| **Ornith-1.5-35B-A3B** | `/models/Ornith-1.5-35B-A3B-Q4_K_M.gguf` | `"--n-cpu-moe 28 --no-mmproj"` | 172032 | ~41 tok/s · sem benchmark divulgado |
| gemma-4-12B-it (rollback) | `/models/gemma-4-12B-it-Q4_K_M.gguf` | (nenhum) | 8192 | ~38 tok/s · denso, 100% GPU (`LLAMA_NGL=99`) |

Ornith e Qwen3.6 são arquiteturalmente quase gêmeos (mesma família híbrida GatedDeltaNet+atenção, MoE 256/8+shared, mesmo tamanho) — por isso o mesmo `--n-cpu-moe 28` funciona igual nos dois, com a mesma folga de VRAM (~800MB livres a 172K de contexto). Pra trocar pro Ornith:
```bash
pct exec 110 -- bash -c 'sed -i "s|Qwen3.6-35B-A3B-UD-Q4_K_M.gguf|Ornith-1.5-35B-A3B-Q4_K_M.gguf|" /etc/llama-server.env && systemctl restart llama-server'
```
(reverter: trocar `Ornith-1.5-35B-A3B-Q4_K_M.gguf` de volta por `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` no comando acima)

**Rollback pro gemma:** config salva em `/etc/llama-server.env.bak-gemma` no próprio LXC — `cp /etc/llama-server.env.bak-gemma /etc/llama-server.env && systemctl restart llama-server` reverte em segundos.

**Bug de GPU corrigido (2026-09-19):** depois de um reboot do LXC, o driver NVIDIA reatribuiu o major number do device `/dev/nvidia-uvm` (de 509 pra 508), mas o cgroup em `/etc/pve/lxc/110.conf` só liberava 509 — CUDA falhava silenciosamente e o llama-server caía pra CPU (sem crash, só ~10x mais lento) sem nenhum log de erro óbvio. Sintoma: `nvidia-smi` mostra 0% de uso e 1 MiB durante geração ativa. Fix: conferir o major real com `ls -la /dev/nvidia-uvm*` e ajustar a linha `lxc.cgroup2.devices.allow: c XXX:* rwm` correspondente no `.conf`, depois `pct reboot`. Pode se repetir em reboots futuros do host.

---

### LXC 9 — Jellyfin (Media Streaming)

- **Services:** Jellyfin (12.1) · Seerr
- **Access:** `192.168.0.218` · `jellyfin.joaopaulo.me` · `seerr.joaopaulo.me`
- **Ports:** 8096 (Jellyfin) · 5055 (Seerr)
- **Resources:** 4 cores · 8 GB RAM · 50 GB disk

Streaming de filmes e séries. Biblioteca montada via NFS do Mini PC (`192.168.0.12:/storage`). Transcoding via CPU por ora — GPU pode ser adicionada depois replicando o passthrough do LXC 8. Seerr (sucessor unificado do Jellyseerr + Overseerr) roda ao lado, na mesma rede Docker — pedidos de mídia conectados ao Jellyfin e ao Radarr/Sonarr (LXC 10); atrás de Cloudflare Access.

Config: [LXC_9_jellyfin/](LXC_9_jellyfin/)

---

### LXC 10 — Arr Stack + Music Automation

- **Services:** Prowlarr · Radarr · Sonarr · Lidarr · Bazarr · slskd · Soularr · Beets
- **Access:** `192.168.0.219` (LAN apenas)
- **Ports:** 9696 · 7878 · 8989 · 8686 · 6767 · 5030 (slskd) · 50300 (Soulseek P2P)
- **Resources:** 2 cores · 2 GB RAM · 20 GB disk

Stack de automação de mídia e música. *arr + Prowlarr para filmes/séries/música via torrents. slskd + Soularr para músicas via Soulseek (Lidarr → Soularr → slskd). Beets para organização de tags. Soularr fala com Lidarr via `http://sb_lidarr:8686` (mesmo LXC). Biblioteca no Mini PC via NFS.

Config: [LXC_10_arr/](LXC_10_arr/)

---

### LXC 11 — Downloads (qBittorrent)

- **Service:** qBittorrent
- **Access:** `192.168.0.220` (LAN apenas)
- **Ports:** 8080 (WebUI) · 6881 TCP+UDP (torrents)
- **Resources:** 2 cores · 4 GB RAM · 20 GB disk

Download client para o stack *arr. Arquivos baixados em `/mnt/media/downloads` (NFS → Mini PC). VPN via Gluetun sidecar é opcional — documentado no readme, não ativo por padrão.

Config: [LXC_11_downloads/](LXC_11_downloads/)

---

### LXC 13 — Camera (motionEye)

- **Service:** motionEye (`motioneyeproject/motioneye`)
- **Access:** `192.168.0.222` · `camera.joaopaulo.me` (pendente — Traefik fora do ar, ver seção LXC 1; recomendado atrás de Cloudflare Access quando restaurado)
- **Port:** 8765
- **Resources:** 2 cores · 1 GB RAM · 512 MB swap · 20 GB disk · webcam USB (passthrough V4L2)

Webcam USB conectada diretamente ao host Proxmox, passada para o LXC via
V4L2 (`/dev/video0`, unprivileged + udev rule para device estável) e daí
para o container Docker via `devices:`. Monitoramento do cachorro via live
view + gravação por movimento na UI do motionEye — sem notificação push por
ora (upgrade fácil pra depois via hooks `on_motion_detected`/`on_movie_end` →
ntfy, já rodando no LXC 3).

Config: [LXC_13_camera/](LXC_13_camera/)

---

## Public Subdomains

All routed via Traefik (LXC 1) + Cloudflare Tunnel. No open inbound ports required.

| Subdomain | Service | LXC |
|-----------|---------|-----|
| `traefik.joaopaulo.me` | Traefik dashboard | LXC 1 |
| `hermes.joaopaulo.me` | Hermes agent dashboard | LXC 2 |
| `odysseus.joaopaulo.me` | Odysseus AI workspace | LXC 3 |
| `litellm.joaopaulo.me` | LiteLLM UI | LXC 4 |
| `monitor.joaopaulo.me` | Uptime Kuma | LXC 7 |
| `dockhand.joaopaulo.me` | Dockhand container UI | LXC 7 |
| `apollo.joaopaulo.me` | Apollo inference API | LXC 8 |
| `langfuse.joaopaulo.me` | Langfuse observabilidade LLM | LXC 4 |
| `jellyfin.joaopaulo.me` | Jellyfin streaming | LXC 9 |
| `seerr.joaopaulo.me` | Seerr (pedidos de mídia) | LXC 9 |
| `camera.joaopaulo.me` | motionEye (dog cam) | LXC 13 |
| `home.joaopaulo.me` | Homepage dashboard | LXC 7 |
| `sp.joaopaulo.me` | Super Productivity | Mini PC |
| `nextcloud.joaopaulo.me` | Nextcloud (WebDAV + cloud) | Mini PC |
| `photos.joaopaulo.me` | Immich (fotos/vídeos) | Mini PC |

---

## Architecture at a Glance

```
Internet / LAN
      │
      ▼
 Cloudflare (DNS + Tunnel)
      │
      ▼
LXC 1 — Traefik (reverse proxy + TLS)
      │
      ├── LXC 2 — Hermes (agent + MCP server)  ◄─── skills, vault (SSHFS → Mini PC)
      │       │
      │       └── LXC 3 — Odysseus (web UI) ──────── consumes MCP
      │
      ├── LXC 4 — LiteLLM (AI router)
      │       ├── LXC 8 — Apollo (local GPU, RTX 3060)
      │       ├── Mac M1 (Ollama, lightweight)
      │       └── OpenRouter (free cloud models)
      │
      ├── LXC 5 — Dados (Postgres · Redis · FalkorDB)
      │
      ├── LXC 7 — Monitor (Uptime Kuma · Dockhand)
      │
      └── Media Stack (sob demanda — Proxmox ligado)
              │
              ├── LXC 9  — Jellyfin
              ├── LXC 10 — Arr (Radarr · Sonarr · Lidarr · Prowlarr · Bazarr)
              ├── LXC 11 — qBittorrent
              └── LXC 10 também: slskd · Soularr · Beets (music automation)
                      │
                      └── NFS ◄──────────────────── Mini PC 192.168.0.12
                                                     /storage/{music,movies,tv,downloads}
                                                     Navidrome (4533) — sempre ligado
                                                     Obsidian LiveSync — já em produção

LXC 13 — Camera (motionEye) ── webcam USB (Proxmox host, V4L2 passthrough)
```

---

## Deferred / Planned

| Item | Notes |
|------|-------|
| LXC 6 dev environment | Low priority — clean Debian + VS Code SSH |
| FalkorDB activation | Enable when Graphify joins the stack |
| Hermes nightly pipeline | Configure schedules once Hermes is stable |
| Vault taxonomy | Obsidian vault structure to be defined |
| Hermes Gateway | Telegram/Discord for mobile second-brain access |
| Gitea | Local GitHub mirror for offline agent access |
| ~~Homepage~~ | ✅ Deployado — `home.joaopaulo.me` (LXC 7 porta 3002) |
| Jellyfin GPU passthrough | Add RTX 3060 to LXC 9 when CPU transcoding is bottleneck |
| Navidrome public subdomain | `music.joaopaulo.me` via Cloudflare Tunnel (LAN-only for now) |
| qBittorrent VPN | Gluetun sidecar — documented in LXC 11 readme, not active |
