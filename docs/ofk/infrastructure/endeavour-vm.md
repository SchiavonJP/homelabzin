---
type: Infrastructure
title: Endeavour VM
description: Personal desktop VM (VM 100, EndeavourOS) migrated from the physical notebook; owns the RTX 3060 via VFIO.
resource: migration/endeavouros/README.md
tags: [proxmox, vm, endeavouros, gpu, gaming]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: migration-readme
    resource: ../../migration/endeavouros/README.md
    title: EndeavourOS VM + Apollo migration record
    author: human:schiva
---

# Overview

VM **100** (`endeavour-vm`) is the user's personal desktop, cloned from the physical notebook (disk image `endeavour-system`) and restored into Proxmox on 2026-10-31. It is used directly (monitor on the RTX 3060, USB keyboard/mouse on the host) and owns the GPU via VFIO since 2026-11-04 — local AI inference moved to CPU on [Apollo](../lxc/lxc-8-llama.md).

# Configuration

| Item | Value |
|------|-------|
| VMID | 100 |
| OS | EndeavourOS (Arch-based), LTS kernel 6.18 |
| Machine | q35 + OVMF (UEFI) |
| CPU | 8 vCPUs, type `host` |
| RAM | 32 GiB fixed (4 GiB staging during migration) |
| Disk | 300 GiB VirtIO SCSI on `local-lvm` (SATA SSD), Btrfs |
| GPU | RTX 3060 passthrough (IOMMU group 9: `10de:2503` + audio `10de:228e`) |
| MAC | `BC:24:11:6C:F6:60` on `vmbr0` |

# History

* 2026-10-29: preflight verified (IOMMU groups, disk inventory).
* 2026-10-31: Clonezilla/Partclone image restored; VM boots desktop.
* 2026-11-10: disk expanded 160 GiB → 300 GiB (`qm resize` + Btrfs resize in guest); verified over SSH.
* GPU passthrough + on-demand inference installer: pending steps recorded in the migration README.

# Rules recorded during migration

* Never attach the original notebook disks directly to this VM.
* No automatic synchronization between the notebook OS install and this VM — they are independent.
* Host directory storage `local` (~5 GiB free) is not an image/backup destination; use `local-lvm`.
* Rollback copies: source notebook disks and the original Apollo LXC config.

# Related

* Migration scripts and evidence: `migration/endeavouros/` (preflight, VM creation, export/import, safety tests).[^migration-readme]

[^migration-readme]: migration/endeavouros/README.md, inventory and progress sections.
