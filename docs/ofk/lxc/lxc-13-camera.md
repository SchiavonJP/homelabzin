---
type: LXC Container
title: LXC 13 — Camera
description: motionEye dog cam — USB webcam passthrough (V4L2) from host to CT114, IP 192.168.0.222.
resource: LXC_13_camera/readme.md
tags: [lxc, camera, motioneye, usb-passthrough]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: lxc-readme
    resource: ../../LXC_13_camera/readme.md
    title: LXC 13 readme — V4L2 passthrough and udev rules
    author: human:schiva
---

# Identity

| Item | Value |
|------|-------|
| VMID | 114 (hostname `sb-camera`) |
| IP | 192.168.0.222 |
| Port | 8765 (motionEye UI) |
| Resources | 2 cores · 1 GB RAM · 512 MB swap · 20 GB disk |
| Access | `camera.joaopaulo.me` — pending ingress gate; recommend behind Cloudflare Access |

# Service

* **motionEye** (`motioneyeproject/motioneye` — maintained fork, **not** `ccrisan/motioneye`): live view + motion-triggered clips of the dog. No push notifications yet — easy upgrade via `on_motion_detected`/`on_movie_end` hooks → ntfy ([Hermes LXC](lxc-2-hermes-mcp.md) runs ntfy on LXC 3's old stack).

# Hardware passthrough

USB webcam (Aveo `1871:0142`) attached to the Proxmox host, passed to the LXC via V4L2 `/dev/video0`, then into Docker via `devices:`. Key details:[^lxc-readme]

* Always use the `by-id` symlink `-video-index0` (capture node); `-video-index1` is metadata-only.
* udev rule `/etc/udev/rules.d/99-webcam-lxc.rules` pins a stable `video-dogcam` symlink with OWNER/GROUP matching the unprivileged LXC mapping.
* Frigate (AI object detection) was evaluated and **rejected**: GPU VRAM is owned by the [Endeavour VM](../infrastructure/endeavour-vm.md) and CPU detection is too slow for one camera. Revisit if false positives pile up.

[^lxc-readme]: LXC_13_camera/readme.md.
