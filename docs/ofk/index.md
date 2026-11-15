---
okf_version: "0.2"
---

# Homelabzin Knowledge Base

Knowledge bundle for the homelab: Proxmox host, LXC containers, Mini PC services, and operational playbooks. Format is [OKF v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) — human-readable, agent-parseable, git-diffable, Obsidian-friendly.

Every concept carries `generated` (who wrote it) and `verified` (who confirmed it) frontmatter. Trust tiers: no `verified` = unverified; `process:`/agent verifiers = machine-confirmed; `human:schiva` = human-reviewed.

## Infrastructure

* [Proxmox Host](infrastructure/proxmox-host.md) - Main server, all LXC containers + GPU passthrough (192.168.0.200)
* [Mini PC CasaOS](infrastructure/minipc-casaos.md) - 24/7 storage owner, Traefik + Cloudflare Tunnel, NFS export (192.168.0.12)
* [Endeavour VM](infrastructure/endeavour-vm.md) - Personal desktop VM (VM 100), migrated from notebook
* [Dokploy Host](infrastructure/dokploy-host.md) - CT234 (192.168.0.234): Dokploy deployment platform

## LXC Containers

* [LXC 2 — Hermes MCP](lxc/lxc-2-hermes-mcp.md) - AI agent engine + MCP server (CT107)
* [LXC 4 — LiteLLM](lxc/lxc-4-litellm.md) - LLM router + Langfuse + UFSC VPN (CT105)
* [LXC 5 — Dados](lxc/lxc-5-dados.md) - Postgres, Redis, FalkorDB (CT104)
* [LXC 7 — Monitor Stack](lxc/lxc-7-docker-stack.md) - Uptime Kuma, Dockhand, Homepage
* [LXC 8 — Apollo](lxc/lxc-8-llama.md) - bge-m3 CPU embeddings (CT110)
* [LXC 9 — Jellyfin](lxc/lxc-9-jellyfin.md) - Media streaming (CT111)
* [LXC 10 — Arr Stack](lxc/lxc-10-arr.md) - Media/music automation (CT112)
* [LXC 11 — Downloads](lxc/lxc-11-downloads.md) - qBittorrent (CT113)
* [LXC 12 — Personal Hub](lxc/lxc-12-personal-hub.md) - AFFiNE, Hawser, Ryot (CT106)
* [LXC 13 — Camera](lxc/lxc-13-camera.md) - motionEye dog cam (CT114)

## Services

* [Traefik (Mini PC)](services/traefik-minipc.md) - Reverse proxy + TLS for all public subdomains
* [LiteLLM Router](services/litellm.md) - Single OpenAI-compatible endpoint, 9 approved aliases
* [Dados Data Layer](services/dados.md) - Postgres/Redis/FalkorDB connection reference
* [Xereta](services/xereta.md) - Knowledge review application (own repo)
* [Dockhand](services/dockhand.md) - Docker container management UI
* [Uptime Kuma](services/uptime-kuma.md) - HTTP/TCP/SSL monitoring
* [Homepage](services/homepage.md) - Central dashboard

## Playbooks

* [Bootstrap LXC](playbooks/bootstrap-lxc.md) - Standard sequence to prepare a fresh LXC
* [Deploy Xereta via Dokploy](playbooks/deploy-xereta-dokploy.md) - Dokploy deployment runbook (host .234)

## Conventions

* Actor convention: `human:schiva`, `process:<id>` (e.g. `process:hindsight-nightly`), `<producer>/<version>` for agents.
* Links between concepts use relative markdown paths (Obsidian-compatible).
* Per-claim attribution uses footnotes keyed to `sources[].id`.
* Reserved files: `index.md` (directory listing), `log.md` (update history).
