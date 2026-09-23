# O Debian/Ubuntu remove o plugin eap-peap dos pacotes binários desde a
# 5.8.0-2 (decisão dos mantenedores, ver bug #843180 do Debian) — a UFSC
# exige EAP-PEAP, então não tem como usar o pacote pronto. Build multi-stage
# compilando o strongSwan do zero com --enable-eap-peap.

FROM debian:12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgmp-dev \
    libssl-dev \
    libcap-dev \
    pkg-config \
    flex \
    bison \
    gperf \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG STRONGSWAN_VERSION=5.9.8
WORKDIR /build
RUN wget -q https://download.strongswan.org/strongswan-${STRONGSWAN_VERSION}.tar.gz && \
    tar xzf strongswan-${STRONGSWAN_VERSION}.tar.gz

WORKDIR /build/strongswan-5.9.8
# Lista de plugins ampla o suficiente pra cobrir tudo que já confirmamos
# necessário (rodando de verdade contra a UFSC) + eap-peap, que é o motivo
# de compilar do zero. Sem --disable-defaults — mantém o conjunto padrão
# do upstream e só garante explicitamente o que precisamos.
RUN ./configure \
      --prefix=/usr \
      --sysconfdir=/etc \
      --enable-eap-identity \
      --enable-eap-md5 \
      --enable-eap-gtc \
      --enable-eap-mschapv2 \
      --enable-eap-peap \
      --enable-eap-ttls \
      --enable-eap-tls \
      --enable-eap-radius \
      --enable-openssl \
      --enable-gmp \
      --enable-pem \
      --enable-pkcs1 \
      --enable-pkcs7 \
      --enable-pkcs8 \
      --enable-pkcs12 \
      --enable-x509 \
      --enable-pubkey \
      --enable-revocation \
      --enable-constraints \
      --enable-kernel-netlink \
      --enable-socket-default \
      --enable-stroke \
      --enable-updown \
      --enable-resolve \
      --enable-vici \
      --enable-swanctl \
    && make -j"$(nproc)" \
    && make install DESTDIR=/install

# ── Imagem final ─────────────────────────────────────────────────────────
FROM debian:12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgmp10 \
    libssl3 \
    libcap2 \
    gettext-base \
    iproute2 \
    iputils-ping \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install/ /

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
