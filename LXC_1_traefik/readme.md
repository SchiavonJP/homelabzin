# LXC 1 — Infra

Traefik v3.6 · reverse proxy · TLS automático · ponto de entrada único

## Specs recomendadas do LXC

```
Hostname:   sb-traefik
Password:   (define uma senha root)
Template:   debian-12 (a que já baixaste)

CPU:        1 cores
RAM:        512 MB 
Swap:       512 MB
Disk:       5 GB    (em qualquer storage que tenhas disponível)

Network:    vmbr0, DHCP  (ou IP fixo se preferires)
DNS:        deixa herdar do host

Name: eth0
Bridge: vmbr0
IPv4: Static
IPv4/CIDR: 192.168.0.212/24
Gateway: 192.168.0.1
```

## Pré-requisitos

```bash
# LXC Debian 12 com nesting=1
# features: keyctl=1,nesting=1  no /etc/pve/lxc/<id>.conf

apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh

# htpasswd para gerar auth do dashboard
apt install -y apache2-utils
```

## Deploy via Git

### 1. SSH access (run once from Proxmox host)

```bash
pct exec <VMID> -- mkdir -p /root/.ssh
cat ~/.ssh/id_ed25519.pub | pct exec <VMID> -- tee /root/.ssh/authorized_keys
pct exec <VMID> -- chmod 700 /root/.ssh
pct exec <VMID> -- chmod 600 /root/.ssh/authorized_keys
```

### 2. Clone only this folder (run on LXC 1)

```bash
git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/homelabzin.git
cd homelabzin
git sparse-checkout init --cone
git sparse-checkout set LXC_1_traefik
git checkout main
cd LXC_1_traefik
```

### 3. Configure

```bash
cp .env.example .env
nano .env   # fill in DOMAIN, ACME_EMAIL, CF_DNS_API_TOKEN, TRAEFIK_DASHBOARD_AUTH

# Generate dashboard password hash
echo $(htpasswd -nb admin tua_senha) | sed -e s/\\$/\\$\\$/g
```

### 4. Deploy

```bash
docker compose up -d
docker compose ps
docker logs sb_traefik
```

### 5. Pull updates

```bash
cd ~/homelabzin && git pull
cd LXC_1_traefik && docker compose up -d
```

## Cloudflare Tunnel (cloudflared)

### Instalar

```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x cloudflared-linux-amd64
mv cloudflared-linux-amd64 /usr/local/bin/cloudflared
```

### Criar e autenticar o túnel

```bash
cloudflared tunnel login               # abre link no browser — autoriza o domínio
cloudflared tunnel create traefik-tunnel   # anote o tunnel ID
```

### Configurar — arquivo correto é /etc/cloudflared/config.yml

O serviço systemd usa `ExecStart=... --config /etc/cloudflared/config.yml`.
**Não editar `/root/.cloudflared/config.yml`** — o daemon ignora esse arquivo.

```bash
nano /etc/cloudflared/config.yml
```

Conteúdo (substitua o tunnel ID):

```yaml
tunnel: <tunnel-id>
credentials-file: /root/.cloudflared/<tunnel-id>.json
protocol: http2
edge-ip-version: "4"     # string com aspas — inteiro causa erro de parse
no-autoupdate: true

ingress:
  # Dashboard Traefik — passa pelo Traefik com basic auth
  - hostname: traefik-dash.joaopaulo.me
    service: http://localhost:8080
  - hostname: traefik.joaopaulo.me
    service: https://localhost:443
    originRequest:
      noTLSVerify: true
      originServerName: traefik.joaopaulo.me

  # Serviços nos outros LXCs — roteamento direto via HTTP na LAN
  # Cloudflare fornece HTTPS para o usuário; TLS interno desnecessário
  - hostname: hermes.joaopaulo.me
    service: http://192.168.0.213:9119
  - hostname: litellm.joaopaulo.me
    service: http://192.168.0.211:4000
  - hostname: odysseus.joaopaulo.me
    service: http://192.168.0.214:7000

  - service: http_status:404
```

### Criar registros DNS (uma vez por hostname)

```bash
cloudflared tunnel route dns traefik-tunnel traefik-dash.joaopaulo.me
cloudflared tunnel route dns traefik-tunnel traefik.joaopaulo.me
cloudflared tunnel route dns traefik-tunnel hermes.joaopaulo.me
cloudflared tunnel route dns traefik-tunnel litellm.joaopaulo.me
cloudflared tunnel route dns traefik-tunnel odysseus.joaopaulo.me
```

### Instalar serviço systemd

```bash
cloudflared service install
systemctl enable cloudflared
systemctl start cloudflared
```

### Corrigir 502 intermitentes (instabilidade QUIC)

O `protocol: http2` no config.yml é ignorado pelo systemd. Forçar via env:

```bash
systemctl edit cloudflared
# adicionar e salvar:
[Service]
Environment="TUNNEL_TRANSPORT_PROTOCOL=http2"
```

```bash
systemctl restart cloudflared
```

### Regras importantes

- cloudflared **não faz hot-reload** — qualquer mudança exige `systemctl restart cloudflared`
- O arquivo que o daemon lê é `/etc/cloudflared/config.yml` (não `/root/.cloudflared/`)
- Para serviços em outros LXCs na mesma LAN, rotear direto via HTTP é mais simples e funciona
- Adicionar novo hostname: editar config + `cloudflared tunnel route dns` + restart




## Domínio — opções

### Opção A — Domínio próprio
Aponta o DNS do teu domínio para o IP público do servidor.
Cada subdomínio (traefik., litellm., odysseus., hermes.) precisa de um A record.

### Opção B — DuckDNS (gratuito, sem domínio próprio)
```bash
# Regista em https://www.duckdns.org
# Cria um subdomínio: teu-nome.duckdns.org
# Aponta para o IP público do servidor
# No .env: DOMAIN=teu-nome.duckdns.org
```

### Opção C — Acesso só interno (sem domínio público)
Usa IP direto ou configura um domínio local com /etc/hosts no Mac:
```
<IP_LXC1>  traefik.local litellm.local odysseus.local hermes.local
```
Neste caso comenta as linhas de TLS e usa HTTP simples.

## Estrutura de subdomínios

| Subdomínio              | Serviço         | LXC |
|-------------------------|-----------------|-----|
| traefik.teu-dominio.com | Dashboard Traefik | LXC 1 |
| litellm.teu-dominio.com | AI Router UI    | LXC 4 |
| odysseus.teu-dominio.com| Odysseus        | LXC 3 |
| hermes.teu-dominio.com  | Hermes          | LXC 2 |

## Adicionar novos serviços

Quando adicionares um serviço novo (ex: FalkorDB browser), basta adicionar
em `dynamic/services.yml` e o Traefik detecta automaticamente sem restart:

```yaml
http:
  routers:
    falkordb:
      rule: "Host(`falkordb.teu-dominio.com`)"
      entrypoints: [websecure]
      tls:
        certResolver: letsencrypt
      service: falkordb
      middlewares: [secure-headers, rate-limit-admin]

  services:
    falkordb:
      loadBalancer:
        servers:
          - url: "http://<IP_LXC5>:3000"
```

## Middlewares disponíveis

| Middleware       | Uso                                      |
|------------------|------------------------------------------|
| secure-headers   | Headers de segurança — aplica em tudo    |
| rate-limit-api   | 100 req/min — endpoints de AI            |
| rate-limit-admin | 20 req/min — UIs de administração        |

## Verificação de TLS

```bash
# Verificar certificado
curl -vI https://traefik.teu-dominio.com 2>&1 | grep -E "subject|issuer|expire"
```