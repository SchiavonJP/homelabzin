---
type: Playbook
title: Bootstrap LXC
description: Standard sequence to prepare a freshly created Proxmox LXC before deploying its stack.
resource: ../../HOMELAB.md
tags: [proxmox, lxc, bootstrap, docker]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: homelab-md
    resource: ../../HOMELAB.md
    title: HOMELAB.md — Bootstrap padrão de um novo LXC
    author: human:schiva
---

# Trigger

A new LXC was created (`pct create` done) and needs preparation before its stack deploy. Run from the Proxmox host (`ssh root@192.168.0.200`). Replace `<VMIDs>` / `<IPs>` — loops handle several containers at once.

# Steps

## 1. Root password (VNC/noVNC fallback access)

```bash
for ID in <VMIDs>; do
    pct exec $ID -- passwd root
done
```

## 2. Enable Docker (nesting + keyctl) and reboot

Redundant if the LXC was created with `--features keyctl=1,nesting=1` (default for recent LXCs).

```bash
for ID in <VMIDs>; do
    echo "features: keyctl=1,nesting=1" >> /etc/pve/lxc/${ID}.conf
    pct reboot $ID
done
```

## 3. Inject SSH keys (passwordless access + git clone)

```bash
for ID in <VMIDs>; do
    pct exec $ID -- mkdir -p /root/.ssh
    cat ~/.ssh/id_ed25519.pub | pct exec $ID -- tee /root/.ssh/authorized_keys
    cat ~/.ssh/id_ed25519     | pct exec $ID -- tee /root/.ssh/id_ed25519
    pct exec $ID -- chmod 700 /root/.ssh
    pct exec $ID -- chmod 600 /root/.ssh/authorized_keys /root/.ssh/id_ed25519
done
```

The private key must be registered on GitHub (Settings → SSH keys) for the LXC to clone repos via SSH.

## 4. Install Docker (via IP, after keys are in)

```bash
for IP in <IPs>; do
    ssh root@$IP "apt-get update -qq && apt-get install -y curl"
done
for IP in <IPs>; do
    ssh root@$IP "curl -fsSL https://get.docker.com | sh"
done
```

## 5. Deploy the stack

Sparse checkout of the LXC folder from GitHub, then `docker compose up -d`. Pattern:

```bash
git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/homelabzin.git
cd homelabzin
git sparse-checkout init --cone
git sparse-checkout set LXC_<n>_<name>
git checkout main
```

Follow the per-LXC readme for stack-specific steps.

# Later password change (without full bootstrap)

```bash
pct exec <VMID> -- passwd root                                  # interactive
pct exec <VMID> -- bash -c "echo 'root:NOVASENHA' | chpasswd"   # direct
```

# Notes

* Deploy readmes were repointed from the old repo name (`second-brain-automation`) to `homelabzin` on 2026-11-15; existing checkouts on the LXCs (e.g. `/root/homelabzin` cloned under the old name) should be re-cloned or their `origin` updated on next deploy.[^homelab-md]
* Unprivileged LXCs needing the Mini PC media library use the host-side NFS + `mp0` bind-mount pattern — see [LXC 9 — Jellyfin](../lxc/lxc-9-jellyfin.md).

[^homelab-md]: HOMELAB.md, bootstrap section.
