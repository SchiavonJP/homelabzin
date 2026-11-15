# Homelabzin — Agent Context

## Source of truth

The OKF v0.2 knowledge bundle at **`docs/ofk/`** is the authoritative, agent-parseable documentation. Every concept is markdown with frontmatter (`type`, `status`, `generated`, `verified`, `sources`).

Start at `docs/ofk/index.md`. Concept types: `Infrastructure`, `LXC Container`, `Service`, `Playbook`.

- Before claiming facts about a container/service, read its concept and the `resource` it points to.
- `verified: human:schiva` = human-reviewed; only `process:`/agent verifiers = machine-confirmed; nothing = unverified — say so.
- Update `docs/ofk/log.md` when you change bundle content.

## Actor convention (for frontmatter you write)

- Human: `human:schiva`
- Automated process: `process:<id>` (e.g. `process:hindsight-nightly`)
- Agent/tool: `<producer>/<version>`

## Inventory (verified 2026-11-14 via `pct list`)

> Repo folder `LXC_<n>_*` numbering ≠ Proxmox VMID. Resolve through the table in `docs/ofk/infrastructure/proxmox-host.md`.

| VMID | Name | IP | Role |
|------|------|----|------|
| 100 | endeavour-vm (VM) | — | Personal desktop, RTX 3060 via VFIO |
| 104 | sb-dados | 192.168.0.210 | Postgres 17, Redis 7, FalkorDB |
| 105 | sb-litellm | 192.168.0.211 | LiteLLM router + Langfuse + UFSC VPN |
| 106 | personal-hub | 192.168.0.221 | AFFiNE, Hawser, Ryot |
| 107 | sb-hermes | 192.168.0.213 | Hermes agent, MCP server (:3100), Xereta (:3101) |
| 108 | sb-odysseus | — | **Retired** (stopped) |
| 109 | sb-monitor | 192.168.0.216 | Uptime Kuma, Dockhand, Homepage |
| 110 | apollo | 192.168.0.217 | bge-m3 CPU embeddings (:8081), `embed` alias |
| 111–113 | sb-media / sb-arr / sb-downloads | .218/.219/.220 | Media stack — stopped when unused |
| 114 | sb-camera | 192.168.0.222 | motionEye dog cam |
| 230–233 | pncp-* | .230–.233 | Liciteria POC (stopped) |
| 234 | dokploy | 192.168.0.234 | Dokploy deployment host |

Reverse proxy (Traefik + Cloudflare Tunnel) runs on the **Mini PC** (`192.168.0.12`, CasaOS) — LXC 1 no longer exists. Mini PC also owns NFS `/storage` export and Obsidian LiveSync (CouchDB — do not touch).

## Key rules

- Xereta is moving to its own repo (`github.com/SchiavonJP/xereta`) and to Dokploy deployment — see `docs/ofk/playbooks/deploy-xereta-dokploy.md`.
- LiteLLM approved catalog (2026-11-09): `default-agent`, `coder`, `fast`, `reasoning`, `generalist`, `vision`, `frontier`, `ocr`, `embed`. No fallback exists for `embed`.
- `docs/ofk/` links use relative paths (Obsidian-compatible); keep it that way.
- Deploy pattern per LXC: sparse checkout of its folder from this repo + `docker compose up -d`.
