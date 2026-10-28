#!/usr/bin/env bash
# Creates a stopped, network-disconnected staging VM. Never restores disks.
set -euo pipefail
[[ $EUID == 0 && -d /etc/pve ]] || { echo 'Run as root on Proxmox.' >&2; exit 1; }
[[ $# == 1 && $1 == local:iso/*.iso ]] || {
  echo 'Usage: bash create-vm.sh local:iso/<verified-Clonezilla-ISO>.iso' >&2; exit 2;
}
iso=$1
iso_path=$(pvesm path "$iso")
[[ -f $iso_path ]] || { echo 'ISO not found.' >&2; exit 1; }
pvesm status --storage local-lvm | awk '
  NR > 1 && $3 == "active" && $6 >= 188743680 { ok=1 }
  END { exit !ok }' || { echo 'Need active local-lvm with at least 180 GiB free.' >&2; exit 1; }
vmid=$(pvesh get /cluster/nextid)
[[ $vmid =~ ^[0-9]+$ ]] || exit 1
qm create "$vmid" --name endeavour-vm --machine q35 --bios ovmf \
  --cpu host --sockets 1 --cores 8 --memory 4096 --balloon 0 \
  --scsihw virtio-scsi-single --scsi0 local-lvm:160,discard=on,ssd=1 \
  --efidisk0 local-lvm:1,efitype=4m,pre-enrolled-keys=0 \
  --ide2 "$iso,media=cdrom" --boot 'order=ide2;scsi0' \
  --net0 virtio,bridge=vmbr0,link_down=1 --onboot 0 --agent enabled=1
echo "Created VM $vmid (stopped, NIC disconnected, 4 GiB RAM)."
echo 'Record this ID. Inspect qm config before starting. No GPU is attached.'
