#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

DUMP=$1  # caminho pro .sql.gz gerado pelo backup.sh

source .env
gunzip -c "$DUMP" | docker exec -i ryot_postgres psql -U ryot -d ryot

echo "Restore aplicado a partir de $DUMP"
