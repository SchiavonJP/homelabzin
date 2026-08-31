#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

DEST=${1:-/mnt/backups/affine}
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DEST"

source .env
docker exec affine_postgres pg_dump -U affine affine | gzip > "$DEST/affine-db-$STAMP.sql.gz"
tar czf "$DEST/affine-storage-$STAMP.tar.gz" -C data storage
tar czf "$DEST/affine-config-$STAMP.tar.gz" config

echo "Backup salvo em $DEST (db + storage + config, $STAMP)"

# Retenção: mantém os últimos 14 dias
find "$DEST" -name 'affine-*-*.gz' -mtime +14 -delete
