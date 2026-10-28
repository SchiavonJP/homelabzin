#!/usr/bin/env bash
# Stage permanent GPU ownership for the next host boot. Does not reboot/unbind.
set -euo pipefail
die() { echo "$*" >&2; exit 1; }
[[ $EUID == 0 && -d /etc/pve ]] || die 'Run as root on Proxmox.'
[[ $# == 2 ]] || die 'Usage: bash configure-vfio.sh <GPU-BDF> <GPU-audio-BDF> (include 0000: domain)'
gpu=$1 audio=$2
for bdf in "$gpu" "$audio"; do
  [[ $bdf =~ ^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$ ]] || die 'Invalid PCI BDF.'
  [[ -e /sys/bus/pci/devices/$bdf/iommu_group ]] || die "No IOMMU group for $bdf."
  [[ $(cat "/sys/bus/pci/devices/$bdf/vendor") == 0x10de ]] || die 'Expected NVIDIA functions.'
done
[[ $(cat "/sys/bus/pci/devices/$gpu/class") == 0x030000 ]] || die 'First function must be a VGA controller.'
[[ $(cat "/sys/bus/pci/devices/$audio/class") == 0x040300 ]] || die 'Second function must be GPU audio.'
[[ ${gpu%.*} == "${audio%.*}" ]] || die 'GPU and audio must belong to the same PCI device.'
for bdf in "$gpu" "$audio"; do
  for device in /sys/bus/pci/devices/"$bdf"/iommu_group/devices/*; do
    member=${device##*/}
    class=$(cat "$device/class")
    [[ $member == "$gpu" || $member == "$audio" || $class == 0x0604* ]] || die "Unsafe group: additional device $member."
  done
done
ids=()
for bdf in "$gpu" "$audio"; do
  vendor=$(cat "/sys/bus/pci/devices/$bdf/vendor")
  device_id=$(cat "/sys/bus/pci/devices/$bdf/device")
  count=0
  for device in /sys/bus/pci/devices/*; do
    if [[ $(cat "$device/vendor") == "$vendor" && $(cat "$device/device") == "$device_id" ]]; then
      count=$((count + 1))
    fi
  done
  [[ $count == 1 ]] || die 'Duplicate PCI IDs found; use a device-specific binding procedure instead.'
  ids+=("${vendor#0x}:${device_id#0x}")
done
[[ -f /etc/initramfs-tools/modules ]] || die 'Expected Proxmox initramfs-tools configuration.'
[[ ! -e /etc/modprobe.d/endeavour-vfio.conf ]] || die 'VFIO configuration already exists; inspect before repeating.'
backup="/root/endeavour-vfio-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -m 0700 "$backup"
cp -a /etc/initramfs-tools/modules "$backup/modules"
printf '%s\n' "$gpu" "$audio" > "$backup/devices"
printf 'options vfio-pci ids=%s,%s\nsoftdep nvidia pre: vfio-pci\nsoftdep nouveau pre: vfio-pci\n' \
  "${ids[0]}" "${ids[1]}" > /etc/modprobe.d/endeavour-vfio.conf
for module in vfio vfio_iommu_type1 vfio_pci; do
  if ! grep -qxF "$module" /etc/initramfs-tools/modules; then
    printf '%s\n' "$module" >> /etc/initramfs-tools/modules
  fi
done
echo "Rollback files: $backup"
update-initramfs -u -k all
echo 'Staged only. Verify Apollo is stopped, host display uses iGPU, and SSH works before rebooting.'
echo 'After reboot, BOTH functions must show Kernel driver in use: vfio-pci.'
