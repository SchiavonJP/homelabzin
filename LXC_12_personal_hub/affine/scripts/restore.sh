#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

STAMP=$1  # timestamp usado no nome dos arquivos gerados pelo backup.sh
DEST=${2:-/mnt/backups/affine}

source .env
gunzip -c "$DEST/affine-db-$STAMP.sql.gz" | docker exec -i affine_postgres psql -U affine -d affine
tar xzf "$DEST/affine-storage-$STAMP.tar.gz" -C data
tar xzf "$DEST/affine-config-$STAMP.tar.gz"

echo "Restore aplicado a partir de $STAMP — reinicie a stack: docker compose up -d"
