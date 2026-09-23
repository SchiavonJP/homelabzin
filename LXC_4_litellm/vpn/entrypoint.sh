#!/bin/bash
set -e

if [ -z "${UFSC_USERNAME:-}" ] || [ -z "${UFSC_PASSWORD:-}" ]; then
  echo "ERRO: UFSC_USERNAME / UFSC_PASSWORD não definidos (checar .env)." >&2
  exit 1
fi

envsubst < /etc/ipsec.conf.template > /etc/ipsec.conf
envsubst < /etc/ipsec.secrets.template > /etc/ipsec.secrets
chmod 600 /etc/ipsec.secrets

echo "Iniciando charon..."
ipsec start --nofork &
CHARON_PID=$!

# Espera o daemon subir antes de tentar conectar
sleep 5
echo "Conectando na VPN da UFSC..."
ipsec up ufsc || echo "Primeira tentativa falhou, o watchdog abaixo vai retentar."

# Watchdog: se o túnel cair, tenta reconectar a cada 30s
(
  while true; do
    sleep 30
    if ! ipsec statusall | grep -q "ESTABLISHED"; then
      echo "$(date -Iseconds): túnel UFSC caído, reconectando..."
      ipsec up ufsc || true
    fi
  done
) &

wait "$CHARON_PID"
