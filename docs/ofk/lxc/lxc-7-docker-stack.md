---
type: LXC Container
title: LXC 7 — Monitor Stack
description: Observability tier — Uptime Kuma, Dockhand, Homepage. VMID 109, IP 192.168.0.216.
resource: LXC_7_docker_stack/readme.md
tags: [lxc, monitoring, uptime-kuma, dockhand, homepage]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: lxc-readme
    resource: ../../LXC_7_docker_stack/readme.md
    title: LXC 7 readme — services and monitor list
    author: human:schiva
---

# Identity

| Item | Value |
|------|-------|
| VMID | 109 (hostname `sb-monitor`) |
| IP | 192.168.0.216 |
| Resources | 1 core · 1 GB RAM · 10 GB disk |
| Access | `monitor.joaopaulo.me` (:3001) · `dockhand.joaopaulo.me` (:3000) · `home.joaopaulo.me` (:3002) |

> Repo folder is `LXC_7_docker_stack/` but the VMID is **109**. Added after a 502 debugging session (Jun 2026) that manual diagnosis took 30 min to find — Kuma surfaces it immediately.

# Services

| Container | Port | Role | Concept |
|-----------|------|------|---------|
| `sb_kuma` | 3001 | Uptime Kuma — HTTP/TCP/SSL monitoring | [Uptime Kuma](../services/uptime-kuma.md) |
| `sb_dockhand` | 3000 | Docker container management UI | [Dockhand](../services/dockhand.md) |
| `sb_homepage` | 3002 | Central dashboard | [Homepage](../services/homepage.md) |

Dockhand uses the `dockhand` database on [LXC 5 — Dados](lxc-5-dados.md) (`CREATE DATABASE dockhand;` once).

# Kuma monitor list

Public HTTPS checks on all `*.joaopaulo.me` routes plus LAN TCP checks: Hermes 9119/3100, LiteLLM 4000, Postgres 5432, Redis 6379, Jellyfin 8096, Prowlarr 9696, qBittorrent 8080, Navidrome 4533. Full table in the readme.[^lxc-readme]

# Homepage configuration

Config lives in `LXC_7_docker_stack/homepage/` (`settings.yaml`, `services.yaml`, `widgets.yaml`, `docker.yaml`). Widgets consume API keys via `.env` (Jellyfin, Radarr, Sonarr, Lidarr, qBittorrent, Proxmox token).

[^lxc-readme]: LXC_7_docker_stack/readme.md.
