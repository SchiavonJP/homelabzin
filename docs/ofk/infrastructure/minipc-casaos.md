---
type: Infrastructure
title: Mini PC CasaOS
description: Always-on storage owner and lightweight services host — Traefik + Cloudflare Tunnel entry point, NFS media export, Obsidian LiveSync.
resource: minipc/readme.md
tags: [minipc, casaos, traefik, cloudflare, nfs, storage]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: minipc-readme
    resource: ../../minipc/readme.md
    title: Mini PC readme — services, storage, NFS
    author: human:schiva
  - id: homelab-md
    resource: ../../HOMELAB.md
    title: HOMELAB.md — Mini PC section
    author: human:schiva
---

# Overview

Always-on machine (`192.168.0.12`, CasaOS at port 8888). Owner of the media library and the 24/7 service tier — anything here survives Proxmox being powered down. Since LXC 1 was retired, this machine also runs the reverse proxy ([Traefik](../services/traefik-minipc.md)) and the Cloudflare Tunnel that exposes all public subdomains.

# Storage layout

| Path | Content |
|------|---------|
| `/storage/music` | Music library (Navidrome + Lidarr) |
| `/storage/movies` | Movies (Radarr + Jellyfin) |
| `/storage/tv` | TV shows (Sonarr + Jellyfin) |
| `/storage/downloads` | qBittorrent landing zone |

Exported via the `minipc_nfs` Docker container (`erichough/nfs-server`) to `192.168.0.0/24`. Native `nfs-kernel-server`/`rpcbind` are removed before the container starts. Setup: `minipc/nfs/setup-nfs.sh`.

# Services in execution

| Container | Image | Port | Role |
|-----------|-------|------|------|
| `traefik` | traefik:v3.6 | 80, 443, 8088 | [Reverse proxy](../services/traefik-minipc.md) + TLS |
| `cloudflared` | cloudflared-web | — | [Cloudflare Tunnel](../services/traefik-minipc.md) |
| `obsidian-livesync` | couchdb:3.5.0 | 5984 | Vault sync — **do not touch** |
| `nextcloud` (+ cron, db, redis) | big-bear-nextcloud | 7580 | File cloud / [Xereta](../services/xereta.md) vault bridge |
| `code-server` | code-server:4.106.3 | 8082 | VS Code in browser |
| `minipc_navidrome` | navidrome | 4533 | Music streaming 24/7 |
| `minipc_nfs` | erichough/nfs-server | 2049, 111 | NFS export of `/storage` |
| `tailscale` | tailscale:v1.90.8 | 5252 | VPN access to LAN |
| `immich` | immich-server | 2283 | Photo backup (no ML) |
| `adguard` | adguardhome | 3001, 53 | DNS ad-blocking |
| `vaultwarden` | vaultwarden | — | Password manager |
| `karakeep` | — | — | Bookmark/knowledge capture, feeds [Xereta](../services/xereta.md) |
| `metube` | — | — | YouTube downloader |
| `logseq` | — | — | Knowledge base |
| `silverbullet` | — | — | `space/` vault owner, source for Xereta ingestion |

# NFS consumption from LXCs

Unprivileged LXCs cannot mount NFS directly — the host Proxmox mounts it and passes a bind mount (`mp0: /mnt/minipc-storage,mp=/mnt/media`). Pattern documented in [LXC 9 — Jellyfin](../lxc/lxc-9-jellyfin.md).[^minipc-readme]

```
192.168.0.12:/storage /mnt/minipc-storage nfs defaults,_netdev,nofail,soft,timeo=30 0 0
```

# Obsidian LiveSync (CouchDB, port 5984)

In production — never restart, never change credentials. Stores notes as fragmented blobs, not files. The file-level vault path is Nextcloud's `space/` directory (SilverBullet), bridged to Obsidian via Nextcloud Desktop on the notebook; CouchDB/LiveSync connects Obsidian devices separately. See `minipc/silverbullet/readme.md` for the verified sync path.[^minipc-readme]

[^minipc-readme]: minipc/readme.md, services table and NFS section.
