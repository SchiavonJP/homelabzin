---
type: Service
title: Xereta
description: Portuguese knowledge-review application and agent gateway for the Obsidian/SilverBullet vault — the application lives in its own repository.
resource: https://github.com/SchiavonJP/xereta
tags: [xereta, knowledge, review, vault, hindsight]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: xereta-readme
    resource: https://github.com/SchiavonJP/xereta/blob/main/README.md
    title: Xereta README (application repo)
    author: human:schiva
  - id: xereta-agents
    resource: https://github.com/SchiavonJP/xereta/blob/main/docs/AGENTS.md
    title: Xereta agent context — MCP surface, migration checklist
    author: human:schiva
---

# Overview

Xereta is the review application for the shared Obsidian/SilverBullet vault and read-only AFFiNE sources: questions and knowledge items are reviewed in the frontend, with one file per item in the vault (`space/_AgentKnowledge/`) plus a linked index. Hindsight 1.1.0 handles extraction, retention and consolidation; Xereta owns bounded jobs, questions, owner feedback, publication, review and scheduling.

**As of 2026-11-15 the application lives in its own repository:** [`github.com/SchiavonJP/xereta`](https://github.com/SchiavonJP/xereta) (imported from `apps/xereta/` in a single commit — this repo no longer carries the app). Agent context for the app, including the MCP tool surface and the hardcoded-host migration checklist, is at [`xereta/docs/AGENTS.md`](https://github.com/SchiavonJP/xereta/blob/main/docs/AGENTS.md).

# Deployment facts

| Item | Value |
|------|-------|
| Current host | [LXC 2 — Hermes](../lxc/lxc-2-hermes-mcp.md) (CT107), `192.168.0.213:3101` |
| Checkout | `/root/xereta-app`; private runtime `/root/xereta` |
| Containers | `sb_xereta`, `sb_xereta_worker` (Compose project `xereta`) |
| Database | [Dados](dados.md) — `knowledge_curator`, role `xereta` (CT104) |
| Hindsight bank | `knowledge-vault-pilot` |
| State | persistent volume `xereta_xereta_state` |
| Health | `/health/live`, `/health/ready` (worker heartbeat required) |
| Public UI | `https://xereta.joaopaulo.me` — Cloudflare Tunnel (decided 2026-11-15); origin `192.168.0.213:3101` today → `192.168.0.234:3101` post-Dokploy; Cloudflare Access recommended |

# MCP tool backends (decided 2026-11-16)

The 6 skills/memory tools (`list_skills`, `get_skill`, `search_skills`, `get_user_model`, `get_memory`, `search_memory`) have pluggable backends, `local` (default) or `hermes-mcp`:

| Item | Value |
|------|-------|
| Flags | `XERETA_SKILLS_BACKEND`, `XERETA_MEMORY_BACKEND` (`local` default; flip per group) |
| Local mode | filesystem mounts `/skills` (`XERETA_SKILLS_PATH`) and `/opt/data` (`XERETA_MEMORY_PATH`) — current CT107 deploy |
| Hermes mode | proxy to Hermes MCP `http://192.168.0.213:3100/mcp` (`XERETA_HERMES_MCP_URL`), same-named tools — no mounts; target config for CT234 |
| Auth | optional `XERETA_HERMES_MCP_TOKEN` bearer (Hermes MCP is currently unauthenticated on the LAN) |
| Errors | `hermes_unavailable` 503 (transport), `hermes_tool_error` 502 (tool failure); Hermes' graceful `{"content": null, "message": ...}` passes through unchanged |
| Hermes side | [LXC 2 — Hermes](../lxc/lxc-2-hermes-mcp.md) `sb_mcp` rebuilt 2026-11-16 with the FastMCP streamable-HTTP server (old FastApiMCP/SSE build replaced; flat files backed up as `/root/*.bak-20261116`) |
| Status | **deployed on CT107 (2026-11-16)**: production `:3101` runs in `hermes-mcp` mode end-to-end verified; rollback via `xereta:rollback-20261116` image tag + `.env.bak-20261116` |

# Automation invariants

* Automatic mode off by default after migration; no vault-wide approval ever.
* Budget: 10 distinct note-version attempts / 20 min per day, shared across scheduled and manual runs.
* Original notes are never edited; failed conditional writes preserve human edits.
* Owner-only endpoints: `/api/v1/xereta/automation*`, `/source-catalog`, `/source-selection`, `/review-queue`.[^xereta-readme]

# Planned

* Deployment via [Dokploy](../infrastructure/dokploy-host.md) — runbook: [Deploy Xereta via Dokploy](../playbooks/deploy-xereta-dokploy.md).

[^xereta-readme]: Xereta README in the application repo (github.com/SchiavonJP/xereta).
