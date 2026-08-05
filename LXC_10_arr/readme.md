# LXC 10 — Arr Stack

> **Hostname:** sb-arr  
> **IP:** 192.168.0.219  
> **Acesso:** LAN apenas (sem exposição pública)

Stack de automação de mídia. Todos os serviços usam a biblioteca no Mini PC via NFS.

| Serviço | Porta | Função |
|---------|-------|--------|
| Prowlarr | 9696 | Indexador central (RSS + busca) |
| Radarr | 7878 | Automação de filmes |
| Sonarr | 8989 | Automação de séries |
| Lidarr | 8686 | Automação de música |
| Bazarr | 6767 | Download de legendas |

---

## Criar o LXC no Proxmox

```bash
pct create 110 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst \
  --hostname sb-arr \
  --memory 2048 \
  --swap 512 \
  --cores 2 \
  --rootfs local-lvm:20 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.0.219/24,gw=192.168.0.1 \
  --unprivileged 1 \
  --features keyctl=1,nesting=1
pct start 110
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
ls /mnt/media/  # deve mostrar: music, movies, tv, downloads
```

---

## Deploy

```bash
apt-get update -qq && apt-get install -y curl
curl -fsSL https://get.docker.com | sh

mkdir -p /opt/arr && cd /opt/arr

git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/second-brain-automation.git
cd second-brain-automation
git sparse-checkout init --cone
git sparse-checkout set LXC_10_arr
git checkout main
cd LXC_10_arr

docker compose up -d
```

---

## Configuração via UI (pós-deploy)

### 1. Prowlarr → indexadores

`http://192.168.0.219:9696` — adicionar indexadores (1337x, RARBG mirror, Jackett etc.)

### 2. Prowlarr → conectar aos *arr

Settings → Apps → adicionar:
- Radarr: `http://192.168.0.219:7878` + API key do Radarr
- Sonarr: `http://192.168.0.219:8989` + API key
- Lidarr: `http://192.168.0.219:8686` + API key

### 3. Radarr / Sonarr / Lidarr → download client

Settings → Download Clients → qBittorrent:
- Host: `192.168.0.220`
- Port: `8080`
- Username/Password: conforme configurado no LXC 11

### 4. Radarr → library path

`http://192.168.0.219:7878` → Settings → Media Management:
- Root Folder: `/movies`

### 5. Sonarr → library path

Root Folder: `/tv`

### 6. Lidarr → library path

Root Folder: `/music`

### 7. Bazarr

`http://192.168.0.219:6767` → Settings → Sonarr + Radarr com IPs/API keys locais. Adicionar provedor de legendas (OpenSubtitles, Subdl etc.)

---

## Verificação

```bash
curl http://192.168.0.219:9696/ping  # Prowlarr
curl http://192.168.0.219:7878/ping  # Radarr
curl http://192.168.0.219:8989/ping  # Sonarr
curl http://192.168.0.219:8686/ping  # Lidarr
```
