---
type: LXC Container
title: LXC 8 — Apollo
description: CPU-only embeddings node (bge-m3). VMID 110, IP 192.168.0.217. Chat retired; GPU moved to Endeavour VM.
resource: LXC_8_llama/readme.md
tags: [lxc, ai, embeddings, apollo, llama]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: lxc-readme
    resource: ../../LXC_8_llama/readme.md
    title: LXC 8 readme — CPU-only embedding configuration
    author: human:schiva
    last_modified: 2026-11-04T00:00:00-03:00
---

# Identity

| Item | Value |
|------|-------|
| VMID | 110 (hostname `apollo`) |
| IP | 192.168.0.217 |
| Resources | 8 cores · 4 GiB RAM · 1 GiB swap · 50 GB disk · **no GPU** |
| Endpoint | `http://192.168.0.217:8081/v1/embeddings` (LiteLLM alias `embed`) |
| Boot | `onboot: 1`; `bge-embedding` enabled, chat `llama-server` disabled |

# Current state (2026-11-04)

Embeddings only: bge-m3 Q4_K_M on CPU. `BGE_NGL=0`, `CUDA_VISIBLE_DEVICES=-1`, `LLAMA_ARG_DEVICE=none` (override in `/etc/systemd/system/bge-embedding.service.d/cpu-only.conf`). Output: 1024-dim vectors, ctx 8192 — unchanged from GPU era. The RTX 3060 was moved to the [Endeavour VM](../infrastructure/endeavour-vm.md) via VFIO.

Backups: `/root/apollo-cpu-backup.cDteHs/110.conf` (Proxmox) and `/root/apollo-cpu-backup-dbijbut0/` (inside LXC).

# Warnings

* **Do not run `setup.sh`** on the current state — it reinstalls CUDA, re-enables chat + embeddings, and can overwrite CPU-mode parameters. It is retained for the historical GPU deployment only.[^lxc-readme]
* Historical GPU-era sections in the readme (VRAM offload via `--n-cpu-moe`, model swap table, uvm major-number fix) are kept for reference; the `nvidia-uvm` cgroup lesson still applies to any future GPU LXC.

# Consumers

* [LXC 4 — LiteLLM](lxc-4-litellm.md): `embed` alias → this endpoint. No fallback for embeddings — if Apollo is down, embeddings fail.

[^lxc-readme]: LXC_8_llama/readme.md.
