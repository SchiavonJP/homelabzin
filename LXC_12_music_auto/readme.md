# LXC 12 — Music Automation

> **Hostname:** sb-music-auto  
> **IP:** 192.168.0.221

Pipeline de aquisição e organização de música:
- **slskd** → daemon Soulseek (P2P music)
- **Soularr** → bridge entre Lidarr (LXC 10) e slskd
- **Beets** → tagger e organizador de arquivos de música

### Fluxo completo

```
Lidarr (LXC 10) detecta artista/álbum faltando
    ↓
Soularr busca no slskd (Soulseek)
    ↓
slskd baixa → /downloads/slskd/
    ↓
Lidarr importa → /music/
    ↓
Beets processa tags + renomeia conforme template
    ↓
Navidrome (Mini PC) detecta via scan horário
```

---

## Criar o LXC no Proxmox

```bash
pct create 112 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst \
  --hostname sb-music-auto \
  --memory 2048 \
  --swap 512 \
  --cores 2 \
  --rootfs local-lvm:10 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.0.221/24,gw=192.168.0.1 \
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
ls /mnt/media/music
ls /mnt/media/downloads
```

---

## Deploy

```bash
apt-get update -qq && apt-get install -y curl
curl -fsSL https://get.docker.com | sh

mkdir -p /opt/music-auto && cd /opt/music-auto

git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/second-brain-automation.git
cd second-brain-automation
git sparse-checkout init --cone
git sparse-checkout set LXC_12_music_auto
git checkout main
cd LXC_12_music_auto

cp .env.example .env
nano .env  # preencher LIDARR_API_KEY e SLSKD_*
```

**Antes de subir o stack**, obter a API key do Lidarr:
- `http://192.168.0.219:8686` → Settings → General → Security → API Key

Depois:
```bash
docker compose up -d
```

---

## Configuração pós-deploy

### slskd (primeira vez)

`http://192.168.0.221:5030`

1. Criar conta admin no primeiro acesso
2. Settings → API → gerar API key → colocar no `.env` como `SLSKD_API_KEY`
3. Settings → Soulseek → username/password da conta Soulseek
4. Reiniciar: `docker compose restart slskd soularr`

### Soularr

O Soularr não tem UI própria — ele é configurado via variáveis de ambiente (já no compose). Para ver logs:

```bash
docker logs sb_soularr -f
```

Ele faz polling no Lidarr a cada intervalo definido, busca no slskd, e salva em `/downloads/slskd/`.

### Beets

O Beets é um CLI — não tem UI. Configurar via `/config/config.yaml` (dentro do volume `beets_config`).

Template mínimo de config:
```yaml
directory: /music
library: /config/musiclibrary.db

import:
  move: yes
  write: yes

plugins: fetchart embedart lastgenre

fetchart:
  auto: yes
```

Executar import manual após downloads:
```bash
docker exec -it sb_beets beet import /downloads/slskd/
```

Para processar a biblioteca existente:
```bash
docker exec -it sb_beets beet update
```

---

## Verificação

```bash
# slskd respondendo
curl http://192.168.0.221:5030

# Soularr conectado ao Lidarr
docker logs sb_soularr | tail -20

# Beets funcionando
docker exec sb_beets beet version
```
