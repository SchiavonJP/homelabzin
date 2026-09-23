FROM debian:12-slim

# Pacotes recomendados oficialmente pela UFSC para o cliente IKEv2
# (servicos.setic.ufsc.br, FAQ 5459) — omitido só o strongswan-nm (plugin
# de GUI do NetworkManager, sem uso num container headless).
RUN apt-get update && apt-get install -y --no-install-recommends \
    strongswan \
    strongswan-libcharon \
    strongswan-starter \
    strongswan-charon \
    strongswan-swanctl \
    strongswan-pki \
    libcharon-extra-plugins \
    libcharon-extauth-plugins \
    gettext-base \
    iproute2 \
    iputils-ping \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY ipsec.conf.template /etc/ipsec.conf.template
COPY ipsec.secrets.template /etc/ipsec.secrets.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
