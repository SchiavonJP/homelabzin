---
type: LXC Container
title: LXC 12 — Personal Hub
description: Personal services — AFFiNE, Ryot, Hawser agents, and the Xereta AFFiNE reader. VMID 106, IP 192.168.0.221.
resource: LXC_12_personal_hub/
tags: [lxc, personal, affine, hawser, ryot, xereta]
status: stable
generated: { by: human:schiva, at: 2026-11-15T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-15T00:00:00-03:00 }
stale_after: 2027-11-15T00:00:00-03:00
sources:
  - id: pct-config
    resource: /etc/pve/lxc/106.conf
    title: Verified via Proxmox config + docker ps (2026-11-15)
    author: human:schiva
  - id: affine-readme
    resource: ../../LXC_12_personal_hub/affine/README.md
    title: AFFiNE sub-readme
    author: human:schiva
  - id: hawser-readme
    resource: ../../LXC_12_personal_hub/hawser/README.md
    title: Hawser sub-readme
    author: human:schiva
  - id: ryot-readme
    resource: ../../LXC_12_personal_hub/ryot/README.md
    title: Ryot sub-readme
    author: human:schiva
---

# Identity

| Item | Value |
|------|-------|
| VMID | 106 (hostname `personal-hub`) |
| IP | 192.168.0.221 |
| Resources | 4 cores · 8 GB RAM · 4 GB swap · 60 GB disk |
| Flags | unprivileged, `keyctl=1,nesting=1`, `onboot: 1` |

> Repo folder is `LXC_12_personal_hub/` but the VMID is **106**.

# Services (verified 2026-11-15 via `docker ps`)

| Container | Port | Role |
|-----------|------|------|
| `affine_server` | 3010 | [AFFiNE](https://affine.pro) knowledge workspace — read-only source for Xereta |
| `affine_postgres` / `affine_redis` | internal | AFFiNE own data layer |
| `ryot_app` | 8000 | [Ryot](https://github.com/ignisda/ryot) — self-hosted tracking (media, fitness) |
| `ryot_postgres` | internal | Ryot database |
| `hawser_agent` | 2376 | Hawser agent — image-update badges reported to [Dockhand](../services/dockhand.md) |
| `sb_xereta_affine_reader` | — | [Xereta](../services/xereta.md) AFFiNE reader (deployed from `apps/xereta/affine-reader.compose.yml`) |

# Notes

* AFFiNE here is the **read-only integration source** for Xereta — Xereta replaced AFFiNE as the review interface for the knowledge pilot; AFFiNE documents are never edited by Xereta.
* The home directory also holds the AFFiNE reader working checkouts (`xereta-affine`, `xereta-affine-app`) and the `knowledge-affine-*` scripts mirroring `scripts/` in this repo.
* No public subdomain currently routed; access is LAN-only.
* Per-component setup: see the three sub-readmes (`affine/`, `hawser/`, `ryot/`) referenced in `sources`.
