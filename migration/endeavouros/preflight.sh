#!/usr/bin/env bash
# Read-only inventory. Run on the named machine; save output on your workstation.
set -euo pipefail
case "${1:-}" in
  notebook)
    hostname
    lsblk -b -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL
    findmnt /
    cat /etc/fstab
    df -h / /home /mnt/dados
    if [[ -d /sys/firmware/efi ]]; then echo UEFI; else echo BIOS; fi
    command -v bootctl >/dev/null && bootctl status --no-pager || true
    command -v efibootmgr >/dev/null && efibootmgr -v || true
    pacman -Q | awk '/^(linux|nvidia|cuda|dracut|mkinitcpio|grub|systemd|tailscale|syncthing)/'
    systemctl list-unit-files --state=enabled --no-pager
    ;;
  pve)
    hostname
    free -h
    pvesm status
    qm list
    pct list
    lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
    cat /proc/cmdline
    lspci -nnk
    lsusb
    shopt -s nullglob
    groups=(/sys/kernel/iommu_groups/*)
    ((${#groups[@]})) || { echo 'STOP: no IOMMU groups found.' >&2; exit 1; }
    for group in "${groups[@]}"; do
      echo "IOMMU group ${group##*/}"
      for device in "$group"/devices/*; do lspci -nns "${device##*/}"; done
    done
    ;;
  minipc)
    hostname
    df -h /storage
    docker inspect --format '{{json .Config.Env}}' minipc_nfs
    ;;
  *) echo 'Usage: bash preflight.sh notebook|pve|minipc' >&2; exit 2 ;;
esac
