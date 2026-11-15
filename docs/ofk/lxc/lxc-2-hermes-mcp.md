---
type: LXC Container
title: LXC 2 — Hermes MCP
description: Second-brain engine — Hermes agent, FastAPI MCP server, and Xereta host. VMID 107, IP 192.168.0.213.
resource: LXC_2_hermes_mcp/readme.md
tags: [lxc, ai, hermes, mcp, xereta]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: lxc-readme
    resource: ../../LXC_2_hermes_mcp/readme.md
    title: LXC 2 readme — setup, vault, routing
    author: human:schiva
---

# Identity

| Item | Value |
|------|-------|
| VMID | 107 (hostname `sb-hermes`) |
| IP | 192.168.0.213 |
| Resources | 2 cores · 4 GB RAM · 20 GB disk |
| OS | Debian 12 + Docker (`keyctl=1,nesting=1`) |
| Access | `hermes.joaopaulo.me` · dashboard `:9119` · MCP `:3100` (SSE) · Xereta `:3101` |

> Repo folder is `LXC_2_hermes_mcp/` but the VMID is **107**.

# Services

| Container | Port | Role |
|-----------|------|------|
| `sb_hermes` | 9119 | Hermes agent (Nous Research) — dashboard, memory, skills |
| `sb_mcp` | 3100 | FastAPI MCP server (`fastapi-mcp`), vault + skills tools over SSE |
| `sb_xereta` / `sb_xereta_worker` | 3101 | [Xereta](../services/xereta.md) review application |
| `sb_hawser` | 2376 | Hawser agent — image-update badges reported to [Dockhand](../services/dockhand.md) |

# LLM routing

Hermes uses provider `custom:litellm` at `http://192.168.0.211:4000/v1` (key in `OPENAI_API_KEY`). Persistent config lives in the volume at `/opt/data/config.yaml` — Compose env changes do **not** override it; merge `model-provider.example.yaml` blocks instead. Default alias `generalist`; selectable aliases: `generalist`, `default-agent`, `coder`, `fast`, `reasoning`, `vision`, `frontier`, `ocr`.[^lxc-readme]

# Vault access

* CouchDB LiveSync (`obsidian.joaopaulo.me`, on [Mini PC](../infrastructure/minipc-casaos.md)) — blob storage, never touched directly.
* File-level vault: LXC joined Tailscale and mounts the notebook vault via SSHFS at `/mnt/obsidian-vault` (`fuse.sshfs`, `nofail`, systemd `.mount` — automount unsupported inside LXC). Bind-mounted to the `mcp-server` container as `/vault`.
* Limitation: bridge is live only while the notebook is on with Obsidian open. Verified end-to-end 2026-09-28.[^lxc-readme]

# Dependencies

* [LXC 5 — Dados](lxc-5-dados.md): Postgres (`hermes` db), Redis
* [LXC 4 — LiteLLM](lxc-4-litellm.md): model routing (`:4000/v1`)
* Notebook (Tailscale `100.80.3.58`): SSHFS vault source — see `notebook/readme.md`

# Operations

* Setup wizard once: `docker run -it --rm -v ~/.hermes:/opt/data nousresearch/hermes-agent:latest setup`
* Deploy via sparse checkout of `LXC_2_hermes_mcp` from GitHub.
* Nightly synthesis: `hermes schedule add --cron ...` (native scheduling).
* Health: `curl http://localhost:3100/health`, `curl http://localhost:3100/skills`.

[^lxc-readme]: LXC_2_hermes_mcp/readme.md.
