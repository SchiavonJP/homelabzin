---
type: LXC Container
title: LXC 10 — Arr Stack
description: Media and music automation — Prowlarr, Radarr, Sonarr, Lidarr, Bazarr, FlareSolverr, slskd, Soularr, Beets. VMID 112, IP 192.168.0.219. On-demand.
resource: LXC_10_arr/readme.md
tags: [lxc, media, arr, music, soulseek]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: lxc-readme
    resource: ../../LXC_10_arr/readme.md
    title: LXC 10 readme — services and creation
    author: human:schiva
---

# Identity

| Item | Value |
|------|-------|
| VMID | 112 (hostname `sb-arr`) |
| IP | 192.168.0.219 (LAN only) |
| Resources | 2 cores · 2 GB RAM · 20 GB disk |
| Status | **Stopped by default** — media stack runs on demand |

# Services

| Service | Port | Function |
|---------|------|----------|
| Prowlarr | 9696 | Central indexer (RSS + search) |
| Radarr | 7878 | Movie automation |
| Sonarr | 8989 | TV automation |
| Lidarr | 8686 | Music automation |
| Bazarr | 6767 | Subtitles |
| FlareSolverr | 8191 | Cloudflare bypass for protected indexers |
| slskd | 5030 | Soulseek daemon (P2P music, port 50300) |
| Soularr | — | Bridge Lidarr ↔ slskd (`http://sb_lidarr:8686`, same LXC) |
| Beets | — | Music tagger/organizer (CLI) |

# Flow

Torrent path: Prowlarr → Radarr/Sonarr/Lidarr → [qBittorrent](lxc-11-downloads.md) → NFS `/storage` on [Mini PC](../infrastructure/minipc-casaos.md) → [Jellyfin](lxc-9-jellyfin.md)/Navidrome. Music path: Lidarr → Soularr → slskd (Soulseek). Library bind-mounted same as LXC 9 (`mp0` pattern); write permissions on the Mini PC NFS export are required.[^lxc-readme]

[^lxc-readme]: LXC_10_arr/readme.md.
