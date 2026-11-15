---
type: LXC Container
title: LXC 9 — Jellyfin
description: Media streaming (Jellyfin + Seerr), library on Mini PC via NFS bind mount. VMID 111, IP 192.168.0.218. On-demand — usually stopped.
resource: LXC_9_jellyfin/readme.md
tags: [lxc, media, jellyfin, seerr, nfs]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: lxc-readme
    resource: ../../LXC_9_jellyfin/readme.md
    title: LXC 9 readme — creation and NFS bind mount pattern
    author: human:schiva
---

# Identity

| Item | Value |
|------|-------|
| VMID | 111 (hostname `sb-media`) |
| IP | 192.168.0.218 |
| Resources | 4 cores · 8 GB RAM · 50 GB disk |
| Ports | 8096 (Jellyfin) · 5055 (Seerr) |
| Access | `jellyfin.joaopaulo.me` · `seerr.joaopaulo.me` (behind Cloudflare Access) |
| Status | **Stopped by default** — media stack runs on demand |

# Services

* **Jellyfin** — movie/TV streaming, CPU transcoding (GPU passthrough possible later, replicating the [Apollo](lxc-8-llama.md) pattern).
* **Seerr** — unified media requests (successor of Jellyseerr+Overseerr), wired to Jellyfin and to Radarr/Sonarr on [LXC 10](lxc-10-arr.md).

# Library via NFS bind mount

Unprivileged LXCs cannot mount NFS directly. Pattern (host-side):

```bash
# On Proxmox host (once, shared by LXCs 9/10/11)
apt-get install -y nfs-common
mkdir -p /mnt/minipc-storage
echo "192.168.0.12:/storage /mnt/minipc-storage nfs defaults,_netdev,nofail,soft,timeo=30 0 0" >> /etc/fstab
mount -a

# Per-LXC bind mount
echo "mp0: /mnt/minipc-storage,mp=/mnt/media" >> /etc/pve/lxc/111.conf
pct restart 111
```

Remove any leftover in-guest NFS fstab line: `sed -i '/192.168.0.12/d' /etc/fstab`.[^lxc-readme]

[^lxc-readme]: LXC_9_jellyfin/readme.md.
