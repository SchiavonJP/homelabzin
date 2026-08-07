# LXC 10 — Arr Stack + Music Automation

> **Hostname:** sb-arr  
> **IP:** 192.168.0.219  
> **Acesso:** LAN apenas (sem exposição pública)

| Serviço | Porta | Função |
|---------|-------|--------|
| Prowlarr | 9696 | Indexador central (RSS + busca) |
| Radarr | 7878 | Automação de filmes |
| Sonarr | 8989 | Automação de séries |
| Lidarr | 8686 | Automação de música |
| Bazarr | 6767 | Download de legendas |
| FlareSolverr | 8191 | Bypass Cloudflare (indexadores protegidos) |
| slskd | 5030 | Daemon Soulseek (P2P music) |
| Soularr | — | Bridge Lidarr ↔ slskd |
| Beets | — | Tagger e organizador de música (CLI) |

---

## Criar o LXC no Proxmox

```bash
pct create 112 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst \
  --hostname sb-arr \
  --memory 2048 \
  --swap 512 \
  --cores 2 \
  --rootfs local-lvm:20 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.0.219/24,gw=192.168.0.1 \
  --unprivileged 1 \
  --features keyctl=1,nesting=1
pct start 112
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

**Permissões no Mini PC** (necessário para escrita pelos containers):

```bash
# No Mini PC (192.168.0.12)
sudo mkdir -p /storage/movies /storage/tv /storage/music /storage/downloads /storage/downloads/slskd /storage/downloads/slskd/incomplete
sudo chmod 777 /storage/movies /storage/tv /storage/music /storage/downloads /storage/downloads/slskd /storage/downloads/slskd/incomplete
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

cp .env.example .env
# Preencher LIDARR_API_KEY e SLSKD_API_KEY após primeiro boot
docker compose up -d
```

---

## Configuração via UI

### 1. Prowlarr → FlareSolverr

`http://192.168.0.219:9696` → Settings → Indexers → Add:
- FlareSolverr URL: `http://sb_flaresolverr:8191`

### 2. Prowlarr → indexadores

Adicionar indexadores: 1337x (com FlareSolverr tag), YTS, EZTV, TorrentGalaxy, Nyaa

### 3. Prowlarr → conectar aos *arr

Settings → Apps → adicionar cada *arr:
- Radarr: `http://sb_radarr:7878` + API key
- Sonarr: `http://sb_sonarr:8989` + API key
- Lidarr: `http://sb_lidarr:8686` + API key

### 4. Radarr / Sonarr / Lidarr → download client

Settings → Download Clients → qBittorrent:
- Host: `192.168.0.220`, Port: `8080`

### 5. Radarr → root folder

Settings → Media Management → Root Folders → `/movies`

> **Se o Save travar infinitamente** (bug com NFS): inserir direto no banco:
> ```bash
> apt-get install -y sqlite3
> DB="/var/lib/docker/volumes/lxc_10_arr_radarr_config/_data/radarr.db"
> sqlite3 $DB "INSERT INTO RootFolders (Path) VALUES ('/movies/');"
> docker restart sb_radarr
> ```

### 6. Sonarr → root folder

Root Folder: `/tv`

> **Se o Save travar infinitamente**:
> ```bash
> DB="/var/lib/docker/volumes/lxc_10_arr_sonarr_config/_data/sonarr.db"
> sqlite3 $DB "INSERT INTO RootFolders (Path) VALUES ('/tv/');"
> docker restart sb_sonarr
> ```

### 7. Lidarr → root folder

Root Folder: `/music`

> **Se o Save travar infinitamente**:
> ```bash
> DB="/var/lib/docker/volumes/lxc_10_arr_lidarr_config/_data/lidarr.db"
> sqlite3 $DB "INSERT INTO RootFolders (Path, Name, DefaultMetadataProfileId, DefaultQualityProfileId, DefaultMonitorOption, DefaultNewItemMonitorOption) VALUES ('/music/', 'root', 1, 1, 0, 0);"
> docker restart sb_lidarr
> ```

### 8. Bazarr

`http://192.168.0.219:6767` → Settings → Sonarr + Radarr:
- Sonarr URL: `http://sb_sonarr:8989` + API key
- Radarr URL: `http://sb_radarr:7878` + API key
- Adicionar provedor de legendas: OpenSubtitles ou Subdl

### 9. Jellyfin → bibliotecas

Jellyfin está em LXC 9 (`http://192.168.0.218:8096`).
Settings → Dashboard → Libraries → Add Media Library:
- Movies → `/media/movies`
- TV Shows → `/media/tv`

Jellyfin detecta automaticamente quando Radarr/Sonarr importam novos arquivos.

---

## Configuração de música (slskd + Soularr)

### slskd (primeira vez)

`http://192.168.0.219:5030`
1. Criar conta admin no primeiro acesso
2. Settings → API → gerar API key → colocar no `.env` como `SLSKD_API_KEY`
3. Settings → Soulseek → username/password da conta Soulseek
4. Reiniciar: `docker compose restart slskd soularr`

### Soularr

Configurado via variáveis de ambiente. Após preencher o `.env`:
```bash
docker compose restart soularr
docker logs sb_soularr -f
```

### Beets

CLI para organizar tags. Executar após novos downloads:
```bash
docker exec -it sb_beets beet import /mnt/media/downloads/slskd/
```

---

## Verificação

```bash
curl http://192.168.0.219:9696/ping  # Prowlarr
curl http://192.168.0.219:7878/ping  # Radarr
curl http://192.168.0.219:8989/ping  # Sonarr
curl http://192.168.0.219:8686/ping  # Lidarr
curl http://192.168.0.219:5030       # slskd
```
