#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

DEST=${1:-/storage/backups/karakeep}
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DEST"

# Volume "data" tem o SQLite + anexos/screenshots — é o que importa de verdade.
docker run --rm -v karakeep_data:/data -v "$DEST":/backup alpine \
  tar czf "/backup/karakeep-data-$STAMP.tar.gz" -C /data .

echo "Backup salvo em $DEST/karakeep-data-$STAMP.tar.gz"

# Retenção: mantém os últimos 14 dias
find "$DEST" -name 'karakeep-data-*.tar.gz' -mtime +14 -delete
