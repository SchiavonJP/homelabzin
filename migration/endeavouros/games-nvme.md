# Dedicate the 954 GB NVMe to VM 100 as `/games`

**Goal:** give `endeavour-vm` (VM 100) the unused 953.9 GiB NVMe
(`XPG GAMMIX S11L`, PCI `0000:2b:00.0`, IOMMU group 11) as a native
PCIe passthrough disk, mounted at `/games`.

**Current state (verified 2026-11-22):**

- VM 100 root: `/dev/sda2` Btrfs, 298 GiB, 265 GiB used, **33 GiB free (90%)**.
- NVMe: empty (GPT with zero partitions), SMART PASSED, 4% wear, own IOMMU group.
- Host `local-lvm` is overcommitted (~900 GiB provisioned on a 748 GiB pool);
  do **not** grow the existing VM disk from it.

> The NVMe is formatted on the host **before** passthrough. After passthrough
> the host no longer sees it — that is expected.

---

## Part 1 — host prep (safe while the VM is running)

Run on the Proxmox host as root:

```bash
ssh root@192.168.0.200
```

```bash
set -euo pipefail

# 1. Safety: the disk must be empty and unused
lsblk -o NAME,SIZE,FSTYPE,TYPE,MOUNTPOINT /dev/nvme0n1
wipefs -n /dev/nvme0n1
if mount | grep -q '/dev/nvme0n1'; then
  echo "ABORT: /dev/nvme0n1 is mounted"; exit 1
fi

# 2. One GPT partition spanning the whole disk
sgdisk --zap-all /dev/nvme0n1
sgdisk -n 1:0:0 -t 1:8309 -c 1:games /dev/nvme0n1
blockdev --rereadpt /dev/nvme0n1 || partx -a /dev/nvme0n1
udevadm settle
lsblk -o NAME,SIZE,FSTYPE,TYPE /dev/nvme0n1

# 3. Btrfs filesystem
mkfs.btrfs -f -L games /dev/nvme0n1p1

# 4. Record the UUID (needed for fstab)
blkid -s UUID -o value /dev/nvme0n1p1 | tee /root/games-nvme-uuid.txt
```

Expected: `/dev/nvme0n1p1` is 953.9G, `btrfs`, label `games`.

---

## Part 2 — attach the NVMe (requires VM 100 stopped)

Save your work first: this shuts the desktop down.

### Option A — from the Proxmox web UI shell (phone/laptop)

```bash
set -euo pipefail
qm shutdown 100 --timeout 180
qm set 100 -hostpci4 0000:2b:00.0,pcie=1
qm config 100 | grep '^hostpci4:'
qm start 100
```

### Option B — from inside the VM, detached (survives the shutdown)

The script runs on the host in its own session, so it continues after the
VM (and your SSH/terminal) goes away:

```bash
ssh root@192.168.0.200 'cat > /root/attach-games-nvme.sh' <<'EOF'
#!/bin/bash
set -euo pipefail
qm shutdown 100 --timeout 180
qm set 100 -hostpci4 0000:2b:00.0,pcie=1
qm config 100 | grep '^hostpci4:'
qm start 100
EOF

ssh root@192.168.0.200 \
  'chmod +x /root/attach-games-nvme.sh; setsid nohup /root/attach-games-nvme.sh >/root/attach-games-nvme.log 2>&1 </dev/null & echo started'
```

Check progress from another device / the host:

```bash
cat /root/attach-games-nvme.log
qm status 100
```

---

## Part 3 — inside the VM after reboot

```bash
set -euo pipefail

lsblk -o NAME,SIZE,FSTYPE,TYPE,MOUNTPOINT
UUID=$(sudo blkid -s UUID -o value /dev/nvme0n1p1)
echo "UUID=$UUID"

sudo mkdir -p /games
sudo mount -U "$UUID" /games
sudo chown schiva:schiva /games

if ! grep -q "UUID=$UUID[[:space:]]*/games" /etc/fstab; then
  echo "UUID=$UUID /games btrfs defaults,noatime,compress=zstd:1,nofail 0 0" | sudo tee -a /etc/fstab
fi

sudo systemctl daemon-reload
sudo mount -a
findmnt /games
df -h /games
ls -ld /games

touch /games/.write-test && rm /games/.write-test && echo "write OK"
```

Steam: **Settings → Storage → Add Drive → `/games`** (or create
`/games/SteamLibrary` first).

---

## Rollback

```bash
# stop the VM, detach the device, start it
qm shutdown 100 --timeout 180
qm set 100 --delete hostpci4
qm start 100
```

Inside the guest, remove the `/games` fstab line and the directory. The NVMe
returns to the host and can be reformatted.
