#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

TARBALL=$1  # caminho pro .tar.gz gerado pelo backup.sh

docker compose down
docker run --rm -v karakeep_data:/data -v "$(dirname "$TARBALL")":/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/$(basename "$TARBALL") -C /data"
docker compose up -d

echo "Restore aplicado a partir de $TARBALL"
