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
* Xereta currently deploys via Compose on [LXC 2](../lxc/lxc-2-hermes-mcp.md) (`sb_xereta`, `sb_xereta_worker` at `192.168.0.213:3101`).
* Application repo: `github.com/SchiavonJP/xereta` (split in progress from `apps/xereta/`).

> **Status `draft`:** written ahead of the migration. Verify steps against the live Dokploy UI and update this concept after the first successful deploy.

# Steps

## 1. Prepare the application repo

* Confirm `xereta` repo contains the Dokploy-ready `compose.yml` + `.env.example`.
* Database stays on [Dados](../services/dados.md) CT104 (`knowledge_curator`, role `xereta`) — no new DB.

## 2. Create the Dokploy project

1. Open `http://192.168.0.234` (Dokploy UI).
2. Create a **Compose**-type project named `xereta`.
3. Connect the GitHub repo `SchiavonJP/xereta` (provider auth or deploy key).
4. Point the compose service at the repo's `compose.yml`; set the branch (`main`).

## 3. Environment variables

Fill runtime credentials server-side only (never in the repo): `DATABASE_URL` → `postgresql://xereta:<senha>@192.168.0.210:5432/knowledge_curator`, LiteLLM base/key (`generalist`, `embed`), Hindsight bank `knowledge-vault-pilot`, bearer tokens. Copy values from the current `/root/xereta-app` `.env` on CT107.

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

* ~~Decide final ingress~~ — **decided 2026-11-15**: Cloudflare Tunnel, origin `192.168.0.234:3101` post-cutover (`192.168.0.213:3101` interim). See step 5.
* Document liciteria ("pncp") POC teardown/preservation for CTs 230–233.
* Note: the Xereta AFFiNE reader (`sb_xereta_affine_reader`) runs on CT106 and stays there regardless of where the main app deploys.
* **CT107 coupling (discovered 2026-11-15 from `compose.yml`):** the app uses `network_mode: host` against Hindsight's loopback endpoint, mounts Hermes' own `root_hermes_data` volume read-only, and binds `/root/skills` from CT107's filesystem. Migration to CT234 requires re-provisioning these (or adopting a Hindsight instance + skills on CT234), **or** using Dokploy's remote-server feature to manage the existing CT107 deployment without moving the app. Decide before step 2.
