#!/bin/sh
# SilverBullet writes directly into Nextcloud's local storage. Register those
# changes so Nextcloud Desktop can download them. Run as the Mini PC Docker user.
set -eu
umask 077

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/xereta-nextcloud-sync"
mkdir -p "$state_dir"
chmod 700 "$state_dir"
exec 9>"$state_dir/scan.lock"
flock -n 9 || exit 0

result=0
{
    date -u '+started=%Y-%m-%dT%H:%M:%SZ'
    docker exec --user www-data nextcloud php /var/www/html/occ files:scan \
        --path='schiva/files/Vault' || result=$?
    date -u '+finished=%Y-%m-%dT%H:%M:%SZ'
    printf 'exit_code=%s\n' "$result"
} >"$state_dir/last-scan.log.new" 2>&1
mv "$state_dir/last-scan.log.new" "$state_dir/last-scan.log"
exit "$result"
