---
type: LXC Container
title: LXC 11 — Downloads
description: qBittorrent download client for the arr stack, writes to Mini PC NFS. VMID 113, IP 192.168.0.220. On-demand.
resource: LXC_11_downloads/readme.md
tags: [lxc, media, qbittorrent, downloads]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: lxc-readme
    resource: ../../LXC_11_downloads/readme.md
    title: LXC 11 readme — creation and deploy
    author: human:schiva
---

# Identity

| Item | Value |
|------|-------|
| VMID | 113 (hostname `sb-downloads`) |
| IP | 192.168.0.220 (LAN only) |
| Resources | 2 cores · 4 GB RAM · 20 GB disk |
| Ports | 8080 (WebUI) · 6881 TCP+UDP (torrents) |
| Status | **Stopped by default** — media stack runs on demand |

# Service

* **qBittorrent** — download client for [LXC 10 Arr Stack](lxc-10-arr.md). Files land in `/mnt/media/downloads` (NFS → [Mini PC](../infrastructure/minipc-casaos.md) `/storage/downloads`), then the arr apps move/link them into the library.

# VPN

Gluetun sidecar (VPN) is optional — documented in the readme, **not active** by default.[^lxc-readme]

[^lxc-readme]: LXC_11_downloads/readme.md.
