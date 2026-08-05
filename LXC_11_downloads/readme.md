# LXC 11 — Downloads (qBittorrent)

> **Hostname:** sb-downloads  
> **IP:** 192.168.0.220  
> **Porta WebUI:** 8080

Download client para o stack *arr. Os arquivos baixados vão para `/mnt/media/downloads` (NFS → Mini PC).

---

## Criar o LXC no Proxmox

```bash
pct create 111 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst \
  --hostname sb-downloads \
  --memory 4096 \
  --swap 1024 \
  --cores 2 \
  --rootfs local-lvm:20 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.0.220/24,gw=192.168.0.1 \
  --unprivileged 1 \
  --features keyctl=1,nesting=1
pct start 111
```

---

## Configurar NFS via bind mount (Proxmox host)

LXCs unprivileged não montam NFS diretamente. O NFS é montado no host Proxmox e passado via bind mount.

> Se ainda não fez o setup do host (NFS + fstab no Proxmox), ver LXC_9_jellyfin/readme.md — seção "Configurar NFS".

**No host Proxmox — adicionar bind mount ao config deste LXC:**

```bash
# Substitua NNN pelo ID real deste LXC
echo "mp0: /mnt/minipc-storage,mp=/mnt/media" >> /etc/pve/lxc/NNN.conf
pct restart NNN
```

**Verificar dentro do LXC:**

```bash
ls /mnt/media/downloads  # deve existir e ser gravável
```

---

## Deploy

```bash
apt-get update -qq && apt-get install -y curl
curl -fsSL https://get.docker.com | sh

mkdir -p /opt/downloads && cd /opt/downloads

git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/second-brain-automation.git
cd second-brain-automation
git sparse-checkout init --cone
git sparse-checkout set LXC_11_downloads
git checkout main
cd LXC_11_downloads

cp .env.example .env
docker compose up -d
```

---

## Configuração via UI

`http://192.168.0.220:8080`

Credenciais padrão do linuxserver/qbittorrent: `admin` / ver log de primeiro boot:
```bash
docker logs sb_qbittorrent | grep -i "temporary password"
```

### Configurações recomendadas

- **Downloads → Default Save Path:** `/downloads`
- **Downloads → Keep incomplete torrents in:** `/downloads/incomplete`
- **Connection → Listening port:** 6881 (TCP + UDP)
- **BitTorrent → Seeding → When ratio reaches:** 2.0 (ou conforme sua preferência)
- **Web UI → Authentication:** alterar senha do admin

---

## Adicionar como download client nos *arr

No Radarr/Sonarr/Lidarr (LXC 10, `192.168.0.219`):

Settings → Download Clients → + → qBittorrent:
- Host: `192.168.0.220`
- Port: `8080`
- Username: `admin`
- Password: (a que você definiu)
- Category: `radarr` / `sonarr` / `lidarr` (facilita gerenciamento)

---

## VPN sidecar (opcional)

Se quiser rotear o tráfego do qBittorrent via VPN, adicionar o Gluetun como sidecar no `docker-compose.yml`:

```yaml
  gluetun:
    image: qmcgaw/gluetun:latest
    container_name: sb_gluetun
    cap_add:
      - NET_ADMIN
    devices:
      - /dev/net/tun:/dev/net/tun
    environment:
      VPN_SERVICE_PROVIDER: ${VPN_SERVICE_PROVIDER}
      VPN_TYPE: ${VPN_TYPE}
      WIREGUARD_PRIVATE_KEY: ${WIREGUARD_PRIVATE_KEY}
      SERVER_COUNTRIES: ${SERVER_COUNTRIES}
    ports:
      - "8080:8080"
      - "6881:6881"
      - "6881:6881/udp"
    restart: unless-stopped
```

E no serviço `qbittorrent`:
```yaml
    network_mode: "service:gluetun"  # roteia tráfego pelo Gluetun
```
(remover `ports` do qbittorrent — Gluetun expõe)

---

## Verificação

```bash
curl http://192.168.0.220:8080  # WebUI respondendo
ls /mnt/media/downloads          # diretório acessível
```
