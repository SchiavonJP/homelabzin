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

# strongSwan NÃO usa o bundle de CA do sistema (o do ca-certificates, usado
# por curl/wget) — ele só confia no que estiver em /etc/ipsec.d/cacerts.
# `test -s` em cada passo falha o build alto e claro se o cert não for
# achado/baixado, em vez de deixar a pasta vazia silenciosamente.
RUN mkdir -p /etc/ipsec.d/cacerts && \
    find /usr/share/ca-certificates -iname "*ISRG_Root_X1*" -exec cp {} /etc/ipsec.d/cacerts/isrg-root-x1.pem \; && \
    test -s /etc/ipsec.d/cacerts/isrg-root-x1.pem
# A UFSC usa cadeia da "Generation Y" da Let's Encrypt (intermediária YR1 →
# raiz ISRG Root YR) — raiz nova, ainda não incluída no bundle padrão de
# nenhuma distro (por isso não veio junto com o ca-certificates acima).
# strongSwan só carrega 1 certificado por arquivo — tem que ser arquivo
# separado do isrg-root-x1.pem, não dá pra concatenar num PEM só.
RUN curl -fsSL https://letsencrypt.org/certs/gen-y/root-yr.pem \
      -o /etc/ipsec.d/cacerts/isrg-root-yr.pem && \
    test -s /etc/ipsec.d/cacerts/isrg-root-yr.pem

COPY ipsec.conf.template /etc/ipsec.conf.template
COPY ipsec.secrets.template /etc/ipsec.secrets.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
