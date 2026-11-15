---
type: Service
title: Traefik (Mini PC)
description: Reverse proxy + TLS for all public subdomains — runs on the Mini PC with Cloudflare Tunnel since LXC 1 was retired.
resource: minipc/readme.md
tags: [traefik, cloudflare, tls, reverse-proxy, minipc]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: minipc-readme
    resource: ../../minipc/readme.md
    title: Mini PC readme — traefik and cloudflared containers
    author: human:schiva
  - id: homelab-md
    resource: ../../HOMELAB.md
    title: HOMELAB.md — public subdomains table
    author: human:schiva
---

# Overview

Traefik v3.6 runs as the `traefik` container on the [Mini PC CasaOS](../infrastructure/minipc-casaos.md) (ports 80, 443, 8088), alongside the `cloudflared` container. Since LXC 1 was retired, this is the homelab's single ingress: all `*.joaopaulo.me` traffic arrives via **Cloudflare Tunnel** (no open inbound ports), and Traefik terminates TLS / routes internally.

TLS certificates use the **Cloudflare DNS Challenge** (`CF_DNS_API_TOKEN` with Zone → DNS → Edit). Not the TLS challenge — ports stay closed.

# Routed subdomains

| Subdomain | Service | Where |
|-----------|---------|-------|
| `hermes.joaopaulo.me` | Hermes dashboard | CT107 :9119 |
| `xereta.joaopaulo.me` | [Xereta](xereta.md) | CT107 :3101 (ingress gate pending) |
| `litellm.joaopaulo.me` | [LiteLLM](litellm.md) | CT105 :4000 |
| `langfuse.joaopaulo.me` | Langfuse | CT105 :3001 |
| `monitor.joaopaulo.me` | [Uptime Kuma](uptime-kuma.md) | CT109 :3001 |
| `dockhand.joaopaulo.me` | [Dockhand](dockhand.md) | CT109 :3000 |
| `home.joaopaulo.me` | [Homepage](homepage.md) | CT109 :3002 |
| `jellyfin.joaopaulo.me` | Jellyfin | CT111 :8096 (on-demand) |
| `seerr.joaopaulo.me` | Seerr | CT111 :5055 (on-demand) |
| `camera.joaopaulo.me` | motionEye | CT114 :8765 (gate pending) |
| `nextcloud.joaopaulo.me` | Nextcloud | Mini PC :7580 |
| `photos.joaopaulo.me` | Immich | Mini PC :2283 |
| `sp.joaopaulo.me` | Super Productivity | Mini PC :8083 |
| `obsidian.joaopaulo.me` | Obsidian LiveSync (CouchDB) | Mini PC :5984 — **do not touch** |
| `vault.joaopaulo.me` | Vaultwarden | Mini PC |

# Operational lessons (from the retired LXC 1, still relevant)

* For services on other LXCs, cloudflared can route **directly via HTTP** — Traefik not needed in the path; Cloudflare provides HTTPS to the user.
* `edge-ip-version` must be the quoted string `"4"`.
* cloudflared **does not hot-reload** — `systemctl restart cloudflared` after any config change.
* Each hostname needs a tunnel DNS route: `cloudflared tunnel route dns <tunnel> <hostname>`.
* QUIC instability causes intermittent 502s → `systemctl edit cloudflared`, add `Environment="TUNNEL_TRANSPORT_PROTOCOL=http2"`.
* Reusable middlewares pattern (`secure-headers`, `rate-limit-api`, `rate-limit-admin`) and file provider `watch=true` carry over from the LXC 1 config in `LXC_1_traefik/` (kept in repo for reference).[^homelab-md]

[^homelab-md]: HOMELAB.md — Cloudflared lessons learned.
