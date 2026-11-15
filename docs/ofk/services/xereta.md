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

# Automation invariants

* Automatic mode off by default after migration; no vault-wide approval ever.
* Budget: 10 distinct note-version attempts / 20 min per day, shared across scheduled and manual runs.
* Original notes are never edited; failed conditional writes preserve human edits.
* Owner-only endpoints: `/api/v1/xereta/automation*`, `/source-catalog`, `/source-selection`, `/review-queue`.[^xereta-readme]

# Planned

* Deployment via [Dokploy](../infrastructure/dokploy-host.md) — runbook: [Deploy Xereta via Dokploy](../playbooks/deploy-xereta-dokploy.md).

[^xereta-readme]: Xereta README in the application repo (github.com/SchiavonJP/xereta).
