#!/bin/bash
# NFS via Docker — Mini PC (CasaOS host)
# Run as root on 192.168.0.12
# Usage: sudo bash minipc/nfs/setup-nfs.sh

set -e

# Always work relative to this script's directory (where docker-compose.yml lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# modprobe lives in /sbin which may not be in PATH under "sudo bash"
MODPROBE="$(command -v modprobe 2>/dev/null || echo /sbin/modprobe)"

# ── 1. Free port 111 ────────────────────────────────────────────────────────
echo "==> Parando rpcbind nativo (se instalado)..."
systemctl stop rpcbind rpcbind.socket 2>/dev/null || true
systemctl disable rpcbind rpcbind.socket 2>/dev/null || true
apt-get remove -y rpcbind 2>/dev/null || true

if ss -tlnp | grep -q ':111'; then
  echo "ERRO: porta 111 ainda em uso."
  ss -tlnp | grep ':111'
  exit 1
fi
echo "  OK — porta 111 livre"

# ── 2. Load kernel NFS modules ──────────────────────────────────────────────
echo "==> Carregando módulos de kernel (nfs + nfsd)..."
for mod in nfs nfsd; do
  if ! "$MODPROBE" "$mod" 2>/dev/null; then
    echo "ERRO: módulo '$mod' não disponível."
    echo "Tente: apt-get install linux-modules-extra-\$(uname -r)"
    echo "Ou instale kmod: apt-get install kmod"
    exit 1
  fi
  echo "  OK — $mod"
  grep -qxF "$mod" /etc/modules 2>/dev/null || echo "$mod" >> /etc/modules
done

# ── 3. Storage directories ───────────────────────────────────────────────────
echo "==> Criando diretórios de storage..."
mkdir -p /storage/{music,movies,tv,downloads}

# ── 4. Start container ───────────────────────────────────────────────────────
echo "==> Subindo container NFS em $SCRIPT_DIR ..."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d

echo "==> Aguardando container inicializar (10s)..."
sleep 10

echo "==> Logs:"
docker logs minipc_nfs 2>&1 | tail -15

echo ""
echo "==> Verificação:"
echo "    docker ps | grep minipc_nfs"
echo "    showmount -e localhost"
echo "    showmount -e 192.168.0.12"
