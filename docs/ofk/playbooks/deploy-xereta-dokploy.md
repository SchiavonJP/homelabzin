---
type: Playbook
title: Deploy Xereta via Dokploy
description: Runbook to deploy the Xereta application through the Dokploy instance on CT234 (192.168.0.234).
resource: https://github.com/SchiavonJP/xereta
tags: [xereta, dokploy, deployment, runbook]
status: draft
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-05-14T00:00:00-03:00
sources:
  - id: dokploy-host
    resource: ../infrastructure/dokploy-host.md
    title: Dokploy Host concept
    author: human:schiva
  - id: xereta-service
    resource: ../services/xereta.md
    title: Xereta service concept
    author: human:schiva
---

# Context

* Dokploy runs on [CT234](../infrastructure/dokploy-host.md) (`192.168.0.234`), hand-installed, previously used for the liciteria POC (CTs 230–233, stopped).
* Application repo: **`github.com/SchiavonJP/xereta`** (split completed 2026-11-15; single-commit import from `apps/xereta/`).
* Xereta currently deploys via Compose on [LXC 2](../lxc/lxc-2-hermes-mcp.md) (`sb_xereta`, `sb_xereta_worker` at `192.168.0.213:3101`, `network_mode: host`).
* Public hostname already points at `http://192.168.0.213:3101` via Cloudflare Tunnel.

> **Strategy A (decided 2026-11-15):** re-provision the CT107-local dependencies on CT234 and move the app there. Alternative (Dokploy remote-managing CT107) was rejected to decouple the app from Hermes' host.

# Re-provisioning on CT234 (Strategy A)

The app's MCP endpoint is an agent gateway with filesystem-backed tool groups — see [xereta/docs/AGENTS.md](https://github.com/SchiavonJP/xereta/blob/main/docs/AGENTS.md):

| Dependency | On CT107 today | On CT234 (to provision) |
|-----------|----------------|--------------------------|
| `/skills` (MCP skill tools) | bind mount of `/root/skills` | **not needed anymore** — set `XERETA_SKILLS_BACKEND=hermes-mcp` (2026-11-16); tool reads are proxied to Hermes MCP |
| `/opt/data` (Hermes memory: USER.md, MEMORY.md, synthesis) | read-only mount of Hermes' `root_hermes_data` volume | **not needed anymore** — set `XERETA_MEMORY_BACKEND=hermes-mcp` (2026-11-16); same Hermes MCP proxy. Hindsight bank migration (Hindsight API files) is separate — still planned as a bank copy in step 1 |
| Hindsight (loopback endpoint) | Hindsight instance on CT107 | Hindsight instance on CT234 (own bank; migrate or re-seed the `knowledge-vault-pilot` bank — owner decision) |
| Vault tools (list/read/write notes) | HTTP to vault backends | no change — HTTP-based (SilverBullet on Mini PC, AFFiNE reader on CT106) |
| Postgres | CT104 `knowledge_curator` | unchanged — `192.168.0.210:5432` reachable from CT234 (verified) |

# MCP migration checklist (before cutover)

1. Patch `backend/app/main.py` transport allowlist: add `192.168.0.234:*` to `allowed_hosts` and `http://192.168.0.234:3101` to `allowed_origins` (keep old entries during transition). Checklist lives in the app repo's `docs/AGENTS.md`.
2. Update agent-side configs that connect to `http://192.168.0.213:3101/mcp` → `http://192.168.0.234:3101/mcp` (consumers are configured at runtime on the machines, not in either repo).
3. Cloudflare Tunnel public hostname service field: `http://192.168.0.213:3101` → `http://192.168.0.234:3101`. Hostname/DNS unchanged; cloudflared does not hot-reload — restart the tunnel container.

> **Status `draft`:** written ahead of the migration. Verify steps against the live Dokploy UI and update this concept after the first successful deploy.

# Steps

## 1. Prepare the application repo

* ~~Confirm `xereta` repo contains the Dokploy-ready `compose.yml`~~ — done: `github.com/SchiavonJP/xereta` (compose.yml at repo root; `XERETA_ENV_FILE` default `/root/xereta/.env` becomes Dokploy-managed env).
* Complete the MCP allowlist patch + re-provisioning (see above) before the first CT234 deploy.
* Database stays on [Dados](../services/dados.md) CT104 (`knowledge_curator`, role `xereta`) — no new DB.

## 2. Create the Dokploy project

1. Open `http://192.168.0.234` (Dokploy UI).
2. Create a **Compose**-type project named `xereta`.
3. Connect the GitHub repo `SchiavonJP/xereta` (provider auth or deploy key).
4. Point the compose service at the repo's `compose.yml`; set the branch (`main`).

## 3. Environment variables

Fill runtime credentials server-side only (never in the repo): `DATABASE_URL` → `postgresql://xereta:<senha>@192.168.0.210:5432/knowledge_curator`, LiteLLM base/key (`generalist`, `embed`), Hindsight bank `knowledge-vault-pilot`, bearer tokens. Copy values from the current `/root/xereta-app` `.env` on CT107.

Backend flags for the CT234 deploy (decided 2026-11-16, no mounts needed): `XERETA_SKILLS_BACKEND=hermes-mcp`, `XERETA_MEMORY_BACKEND=hermes-mcp`, `XERETA_HERMES_MCP_URL=http://192.168.0.213:3100/mcp` (CT234 → CT107 over LAN; CT107's `sb_mcp` transport allowlist already includes `192.168.0.234:*`). `XERETA_HERMES_MCP_TOKEN` only if Hermes gains auth.

## 4. Deploy and verify

* Deploy; watch build logs in Dokploy.
* Health: `GET /health/live` and `GET /health/ready` (worker heartbeat must pass).
* Functional: open the UI, confirm review queue and sync-test note flow still work.

## 5. Ingress (decided 2026-11-15)

* **Cloudflare Tunnel** — decision locked: `xereta.joaopaulo.me` → HTTP origin, **no Dokploy-managed SSL**.
* Interim (app on CT107): service target `http://192.168.0.213:3101`.
* After cutover (app on CT234): change only the tunnel service target to `http://192.168.0.234:3101` — hostname/DNS unchanged. Port stays 3101 (`network_mode: host` binds directly).
* Recommend Cloudflare Access in front of the public hostname (owner-review app).
* cloudflared does not hot-reload — restart the tunnel container after config changes.

## 6. Cutover

* Stop `sb_xereta`/`sb_xereta_worker` on CT107 only after the Dokploy deploy is verified.
* Keep the `xereta_xereta_state` volume data path documented — capture snapshots live there; plan the volume migration before cutover.
* Rollback: restart Compose on CT107 (`docker compose up -d`), disable the Dokploy project.

# Verified prerequisites (2026-11-15)

* CT234 → CT104:5432 TCP: **open**. `sb_postgres` binds `0.0.0.0:5432`.

# Open items

* ~~Decide final ingress~~ — **decided 2026-11-15**: Cloudflare Tunnel, origin `192.168.0.234:3101` post-cutover (`192.168.0.213:3101` interim — already active). See step 5.
* ~~Migration strategy~~ — **decided 2026-11-15**: Strategy A (re-provision on CT234). Dependency table above.
* ~~Hermes memory mechanism~~ — **decided 2026-11-16**: no copies, no SSHFS. `hermes-mcp` backends proxy skills/memory reads to Hermes MCP over HTTP; `/skills` and `/opt/data` disappear from the CT234 deploy. CT107's `sb_mcp` was rebuilt for streamable-HTTP with `.234` already in its transport allowlist.
* **Hindsight bank** — fresh instance re-seeded vs migrating the `knowledge-vault-pilot` bank to CT234.
* Document liciteria ("pncp") POC teardown/preservation for CTs 230–233.
* Note: the Xereta AFFiNE reader (`sb_xereta_affine_reader`) runs on CT106 and stays there regardless of where the main app deploys.
