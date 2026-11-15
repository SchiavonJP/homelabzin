---
type: Service
title: Homepage
description: Central homelab dashboard (gethomepage) with service groups, pings and arr widgets. Runs on CT109.
resource: LXC_7_docker_stack/readme.md
tags: [dashboard, homepage]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: lxc-readme
    resource: ../../LXC_7_docker_stack/readme.md
    title: LXC 7 readme — Homepage config
    author: human:schiva
---

# Overview

Homepage (`ghcr.io/gethomepage/homepage`) is the central dashboard at `home.joaopaulo.me` / `192.168.0.216:3002` on [LXC 7 — Monitor Stack](../lxc/lxc-7-docker-stack.md).

# Configuration

| File | Content |
|------|---------|
| `homepage/settings.yaml` | Theme, group layout |
| `homepage/services.yaml` | All services: icons, pings, widgets |
| `homepage/widgets.yaml` | Top widgets (date/time, search) |
| `homepage/docker.yaml` | Auto-discovery (disabled) |

Widgets consume API keys from `.env` (Jellyfin, Radarr, Sonarr, Lidarr, qBittorrent, Proxmox `homepage@pam!homepage` token). Adding a service = edit `services.yaml`; adding a public route = Cloudflare Tunnel → Public Hostname (`home` → `http://192.168.0.216:3002`).[^lxc-readme]

[^lxc-readme]: LXC_7_docker_stack/readme.md.
