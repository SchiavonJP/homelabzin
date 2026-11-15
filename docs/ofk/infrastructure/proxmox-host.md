---
type: Infrastructure
title: Proxmox Host
description: Main homelab server running all LXC containers, the Endeavour VM, and GPU passthrough.
resource: https://192.168.0.200:8006
tags: [proxmox, host, hardware, gpu]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: homelab-md
    resource: ../../HOMELAB.md
    title: HOMELAB.md — hardware and LXC overview
    author: human:schiva
    last_modified: 2026-11-05T00:00:00-03:00
  - id: endeavour-readme
    resource: ../../migration/endeavouros/README.md
    title: EndeavourOS VM + Apollo migration record
    author: human:schiva
---

# Hardware

| Component | Value |
|-----------|-------|
| CPU | Ryzen 5700G (MSI B550M Bazooka) |
| RAM | 64 GB (58 GiB usable) |
| GPU | RTX 3060 12 GB — passed through to [Endeavour VM](endeavour-vm.md) via VFIO since 2026-11-04 |
| Storage | SATA SSD 1 TB (`local-lvm`, ~588 GiB free), HDD, NVMe 953.9 GiB |
| Integrated GPU | AMD (amdgpu) — host display output |

# Access

* Web UI: `https://192.168.0.200:8006`
* SSH: `root@192.168.0.200`
* All LXC management via `pct` / web UI.

# Guest inventory (verified 2026-11-14 via `pct list` / `qm list`)

> **Important mapping note:** the repo's `LXC_<n>_*` folder numbering does **not** match Proxmox VMIDs.
> Always resolve the real VMID through this table.

| VMID | Guest | IP | Status | Role | Concept |
|------|-------|----|--------|------|---------|
| 100 | endeavour-vm | — | running | Personal desktop (EndeavourOS, VM) | [Endeavour VM](endeavour-vm.md) |
| 104 | sb-dados | 192.168.0.210 | running | Databases | [LXC 5 — Dados](../lxc/lxc-5-dados.md) |
| 105 | sb-litellm | 192.168.0.211 | running | LLM router | [LXC 4 — LiteLLM](../lxc/lxc-4-litellm.md) |
| 106 | personal-hub | 192.168.0.221 | running | AFFiNE, Hawser, Ryot | [LXC 12 — Personal Hub](../lxc/lxc-12-personal-hub.md) |
| 107 | sb-hermes | 192.168.0.213 | running | AI agent + MCP | [LXC 2 — Hermes MCP](../lxc/lxc-2-hermes-mcp.md) |
| 108 | sb-odysseus | — | **stopped** | Retired — Odysseus removed from the stack | — |
| 109 | sb-monitor | 192.168.0.216 | running | Kuma, Dockhand, Homepage | [LXC 7 — Monitor Stack](../lxc/lxc-7-docker-stack.md) |
| 110 | apollo | 192.168.0.217 | running | CPU embeddings | [LXC 8 — Apollo](../lxc/lxc-8-llama.md) |
| 111 | sb-media | 192.168.0.218 | stopped | Jellyfin (on-demand) | [LXC 9 — Jellyfin](../lxc/lxc-9-jellyfin.md) |
| 112 | sb-arr | 192.168.0.219 | stopped | Arr stack (on-demand) | [LXC 10 — Arr Stack](../lxc/lxc-10-arr.md) |
| 113 | sb-downloads | 192.168.0.220 | stopped | qBittorrent (on-demand) | [LXC 11 — Downloads](../lxc/lxc-11-downloads.md) |
| 114 | sb-camera | 192.168.0.222 | running | motionEye | [LXC 13 — Camera](../lxc/lxc-13-camera.md) |
| 230–233 | pncp-* | 192.168.0.230–233 | stopped | Liciteria POC stack (app, store, Windmill, Dify) | — |
| 234 | dokploy | 192.168.0.234 | running | [Dokploy](dokploy-host.md) deployment host | [Dokploy Host](dokploy-host.md) |
| 9000 | ubuntu-2204-cloud | — | stopped | Cloud-init template VM | — |

Historical: LXC 1 (Traefik) and LXC 3 (Odysseus) no longer exist in the stack — Traefik moved to the [Mini PC](minipc-casaos.md) with Cloudflare Tunnel; the Odysseus container (CT 108) is kept stopped for rollback. The media stack (111–113) is intentionally stopped when not in use.

# GPU ownership timeline

* 2026-09: RTX 3060 passed through to LXC 110 (Apollo) for llama.cpp inference.
* 2026-11-04: GPU moved to VM 100 (VFIO); Apollo converted to CPU-only embeddings.
* Apollo chat service disabled; embeddings continue at `192.168.0.217:8081`.

# Related knowledge

* NVIDIA driver install guide: `drivers-nvidia.md` (repo root).
* Known issue: after host reboots, the NVIDIA uvm device major number may change — the `lxc.cgroup2.devices.allow` line in affected LXC configs must match (`ls -la /dev/nvidia-uvm*`).[^homelab-md]

[^homelab-md]: HOMELAB.md, LXC 8 historical section.
