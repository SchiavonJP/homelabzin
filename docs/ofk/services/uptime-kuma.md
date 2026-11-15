---
type: Service
title: Uptime Kuma
description: HTTP/TCP/SSL monitoring for all homelab services, public and LAN. Runs on CT109.
resource: LXC_7_docker_stack/readme.md
tags: [monitoring, uptime-kuma]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: lxc-readme
    resource: ../../LXC_7_docker_stack/readme.md
    title: LXC 7 readme — monitor list
    author: human:schiva
---

# Overview

Uptime Kuma (`louislam/uptime-kuma:1`) monitors every service, at `monitor.joaopaulo.me` / `192.168.0.216:3001` on [LXC 7 — Monitor Stack](../lxc/lxc-7-docker-stack.md). A full config backup exists at `LXC_7_docker_stack/kuma-backup.json`.

# Coverage

* Public HTTPS: all `*.joaopaulo.me` routes (Hermes, LiteLLM, Jellyfin, Homepage, Kuma itself…).
* LAN TCP: Hermes 9119/3100, LiteLLM 4000, Postgres 5432, Redis 6379, Jellyfin 8096, Prowlarr 9696, qBittorrent 8080, Navidrome 4533.

# Note

Kuma's monitor table still lists `odysseus.joaopaulo.me` — that service is retired ([CT108 stopped](../infrastructure/proxmox-host.md)); the monitor should be removed or paused during the next Kuma review.[^lxc-readme]

[^lxc-readme]: LXC_7_docker_stack/readme.md.
