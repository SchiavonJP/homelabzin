#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

DEST=${1:-/mnt/backups/ryot}
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DEST"

source .env
docker exec ryot_postgres pg_dump -U ryot ryot | gzip > "$DEST/ryot-db-$STAMP.sql.gz"

echo "Backup salvo em $DEST/ryot-db-$STAMP.sql.gz"

# Retenção: mantém os últimos 14 dias
find "$DEST" -name 'ryot-db-*.sql.gz' -mtime +14 -delete
