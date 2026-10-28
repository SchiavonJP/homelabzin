#!/usr/bin/env bash
# Export live Apollo configuration/models to the verified Mini PC NFS mount.
set -euo pipefail
[[ $EUID == 0 && -d /etc/pve ]] || { echo 'Run as root on Proxmox.' >&2; exit 1; }
[[ $# == 2 && $1 =~ ^[0-9]+$ ]] || {
  echo 'Usage: bash export-apollo.sh <verified-Apollo-CTID> /mnt/endeavour-migration' >&2; exit 2;
}
ctid=$1
mount_root=$(realpath -e "$2")
fstype=$(findmnt -rn -T "$mount_root" -o FSTYPE)
source=$(findmnt -rn -T "$mount_root" -o SOURCE)
[[ $fstype == nfs || $fstype == nfs4 ]] || { echo 'Refusing export to non-NFS storage.' >&2; exit 1; }
[[ $source == 192.168.0.12:/storage ]] || { echo 'Expected Mini PC /storage NFS export.' >&2; exit 1; }
[[ $(pct status "$ctid") == 'status: running' ]] || { echo 'Apollo must be running for export.' >&2; exit 1; }
pct exec "$ctid" -- test -d /models
pct exec "$ctid" -- test -d /opt/llama.cpp/.git
bytes=$(pct exec "$ctid" -- du -sbL /models | awk '{print $1}')
available=$(df -B1 --output=avail "$mount_root" | tail -1 | tr -d ' ')
[[ $bytes =~ ^[0-9]+$ && $available =~ ^[0-9]+$ ]] || exit 1
(( available > bytes + 1073741824 )) || { echo 'Insufficient NFS space for models plus 1 GiB.' >&2; exit 1; }
umask 077
dest="$mount_root/backups/endeavouros/apollo-export-$(date +%Y%m%d-%H%M%S)"
mkdir "$dest" # Refuse a timestamp collision; caller creates parent beforehand.
echo "Exporting CT $ctid to $dest; do not modify/download models during export."
mkdir "$dest/models"
pct config "$ctid" > "$dest/lxc.conf"
pct exec "$ctid" -- git -C /opt/llama.cpp rev-parse HEAD > "$dest/llama-commit.txt"
pct exec "$ctid" -- git -C /opt/llama.cpp diff HEAD > "$dest/llama-local.patch"
pct exec "$ctid" -- git -C /opt/llama.cpp ls-files --others --exclude-standard > "$dest/llama-untracked.txt"
pct exec "$ctid" -- systemctl cat llama-server bge-embedding > "$dest/services.txt"
pct exec "$ctid" -- nvidia-smi > "$dest/nvidia-smi.txt"
pct exec "$ctid" -- tar -C / -cf - \
  etc/llama-server.env etc/bge-embedding.env opt/llama.cpp/run-llama-server.sh \
  > "$dest/runtime-config.tar"
# GNU find/xargs use NUL delimiters, so spaces in model names are safe.
pct exec "$ctid" -- bash -c \
  'cd /models && find -L . -type f -print0 | sort -z | xargs -0 -r sha256sum' \
  > "$dest/models.sha256"
pct exec "$ctid" -- tar -h -C /models -cf - . | tar --no-same-owner -C "$dest/models" -xf -
(cd "$dest/models" && sha256sum --check ../models.sha256)
touch "$dest/EXPORT-VERIFIED"
echo "Verified export: $dest"
echo 'Review live flags, service paths and local/untracked code changes before migration.'
