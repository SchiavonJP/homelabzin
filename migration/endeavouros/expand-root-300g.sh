#!/usr/bin/env bash
# Run in EndeavourOS VM 100, with sudo and an interactive terminal.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
[[ $(hostname) == endeavour-vm ]]
[[ $(findmnt -n -o FSTYPE /) == btrfs ]]
[[ $(findmnt -n -o UUID /) == fe421868-78de-40f5-a0d8-6fa996399c6e ]]
[[ $(blockdev --getsize64 /dev/sda) == 322122547200 ]]
[[ $(lsblk -nro START /dev/sda2) == 4198400 ]]
[[ $(lsblk -nr -o NAME /dev/sda | wc -l) -eq 3 ]]
for mount in / /home /var/cache /var/log /swap; do
    [[ $(findmnt -n -o UUID --target "$mount") == fe421868-78de-40f5-a0d8-6fa996399c6e ]]
done

backup="/root/disk-resize-$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$backup"
sfdisk --dump /dev/sda > "$backup/partition-table.sfdisk"
lsblk -b -o NAME,SIZE,FSTYPE,MOUNTPOINTS /dev/sda > "$backup/lsblk-before.txt"
echo "Partition backup: $backup"
echo 'If prompted to fix the GPT, choose Fix; confirm the in-use partition resize with Yes.'
parted /dev/sda resizepart 2 100%
partprobe /dev/sda
udevadm settle
[[ $(lsblk -nro START /dev/sda2) == 4198400 ]]
[[ $(blockdev --getsize64 /dev/sda2) -gt 319000000000 ]]
btrfs filesystem resize max /
lsblk -b -o NAME,SIZE,FSTYPE,MOUNTPOINTS /dev/sda
btrfs filesystem show /
df -h /
echo 'Completed: partition and Btrfs expanded on VM 100.'
