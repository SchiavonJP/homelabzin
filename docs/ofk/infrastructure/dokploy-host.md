---
type: Infrastructure
title: Dokploy Host
description: LXC CT234 (192.168.0.234) running Dokploy — deployment manager used for the liciteria SaaS POC and planned for Xereta.
resource: 192.168.0.234 (web UI)
tags: [dokploy, deployment, docker, ci-cd, liciteria]
status: stable
generated: { by: human:schiva, at: 2026-11-15T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-15T00:00:00-03:00 }
stale_after: 2027-11-15T00:00:00-03:00
sources:
  - id: pct-inventory
    resource: migration/endeavouros/README.md
    title: Verified via pct list on Proxmox host (2026-11-14)
    author: human:schiva
---

# Overview

LXC **CT 234** (`dokploy`, `192.168.0.234`) runs a hand-installed Dokploy instance — a self-hosted deployment platform (Vercel/Netlify-style) that builds and runs Docker Compose projects from Git repositories.

**Status `stable`:** confirmed by the owner 2026-11-15 — the stopped stack on CTs 230–233 is the *liciteria* SaaS POC (also referred to as "pncp"). Install method, versions, and credentials are still not documented in this bundle; runbook at [Deploy Xereta via Dokploy](../playbooks/deploy-xereta-dokploy.md).

# What runs on it

| Project | Status | Notes |
|---------|--------|-------|
| Liciteria POC ("pncp") | stopped CTs 230–233 | pncp-app, pncp-store, pncp-windmill, pncp-dify (PNCP public-procurement data) |
| [Xereta](../services/xereta.md) | planned | Migration from LXC 2 deployment to Dokploy |

# Verified prerequisites

* CT234 → CT104:5432 TCP reachability: **open** (tested 2026-11-15).
* `sb_postgres` on CT104 binds `0.0.0.0:5432` — reachable from other CTs.

# Related

* Companion CTs 230–233 (`pncp-*`) host the liciteria application components; all stopped as of 2026-11-14.
* Xereta deployment runbook: [Deploy Xereta via Dokploy](../playbooks/deploy-xereta-dokploy.md).
