# LXC 9 — Jellyfin (media streaming)

> **Hostname:** sb-media  
> **IP:** 192.168.0.218  
> **Porta:** 8096  
> **URL pública:** https://jellyfin.joaopaulo.me

Servidor de streaming de filmes e séries. Transcoding via CPU por padrão (GPU pode ser adicionada depois). A biblioteca fica no Mini PC (192.168.0.12) e é montada via NFS.

---

## Criar o LXC no Proxmox

```bash
pct create 111 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst \
  --hostname sb-media \
  --memory 8192 \
  --swap 2048 \
  --cores 4 \
  --rootfs local-lvm:50 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.0.218/24,gw=192.168.0.1 \
  --unprivileged 1 \
  --features keyctl=1,nesting=1
pct start 111
```

---

## Configurar NFS via bind mount (Proxmox host)

LXCs unprivileged não podem montar NFS diretamente. O padrão Proxmox é montar no host e passar via bind mount.

**No host Proxmox (192.168.0.200):**

```bash
apt-get install -y nfs-common
mkdir -p /mnt/minipc-storage

# Adicionar ao /etc/fstab do HOST
echo "192.168.0.12:/storage /mnt/minipc-storage nfs defaults,_netdev,nofail,soft,timeo=30 0 0" >> /etc/fstab
mount -a
ls /mnt/minipc-storage/  # deve mostrar: music, movies, tv, downloads
```

**Adicionar bind mount ao config do LXC (no host Proxmox):**

```bash
# Substitua 111 pelo ID real do LXC 9
echo "mp0: /mnt/minipc-storage,mp=/mnt/media" >> /etc/pve/lxc/111.conf
pct restart 111
```

**Verificar dentro do LXC:**

```bash
ls /mnt/media/  # deve mostrar: music, movies, tv, downloads
```

> Se o LXC já tiver uma linha NFS no `/etc/fstab` interno, remova:
> `sed -i '/192.168.0.12/d' /etc/fstab`

---

## Deploy

```bash
# Dentro do LXC
apt-get update -qq && apt-get install -y curl
curl -fsSL https://get.docker.com | sh

mkdir -p /opt/jellyfin
cd /opt/jellyfin

# Sparse checkout do repo
git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/second-brain-automation.git
cd second-brain-automation
git sparse-checkout init --cone
git sparse-checkout set LXC_9_jellyfin
git checkout main
cd LXC_9_jellyfin

cp .env.example .env
docker compose up -d
```

---

## Traefik — adicionar rota

Em `LXC_1_traefik/dynamic/services.yml`, adicionar:

```yaml
http:
  routers:
    jellyfin:
      rule: "Host(`jellyfin.joaopaulo.me`)"
      entrypoints:
        - websecure
      tls:
        certResolver: letsencrypt
      service: jellyfin
      middlewares:
        - secure-headers

  services:
    jellyfin:
      loadBalancer:
        servers:
          - url: "http://192.168.0.218:8096"
```

---

## Verificação

```bash
# API Jellyfin respondendo
curl http://192.168.0.218:8096/health

# NFS montado e biblioteca visível
ls /mnt/media/movies
ls /mnt/media/tv
```

---

## GPU passthrough (futuro)

Quando quiser ativar transcodificação via RTX 3060, editar `/etc/pve/lxc/111.conf` e adicionar:

```ini
# GPU passthrough — RTX 3060 (compartilhada com LXC 8 Apollo)
lxc.cgroup2.devices.allow: c 195:* rwm
lxc.cgroup2.devices.allow: c 509:* rwm
lxc.cgroup2.devices.allow: c 238:* rwm
lxc.mount.entry: /dev/nvidia0          dev/nvidia0          none bind,optional,create=file
lxc.mount.entry: /dev/nvidiactl        dev/nvidiactl        none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-uvm       dev/nvidia-uvm       none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-uvm-tools dev/nvidia-uvm-tools none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-caps      dev/nvidia-caps      none bind,optional,create=dir
```

Depois reiniciar o LXC e instalar o driver NVIDIA userspace (sem módulo de kernel) — ver `LXC_8_llama/setup.sh` como referência.

No Jellyfin: Settings → Dashboard → Playback → Hardware Acceleration → NVENC.

---

## Configuração inicial do Jellyfin (UI)

1. Acessar `http://192.168.0.218:8096` (ou `https://jellyfin.joaopaulo.me`)
2. Criar usuário admin
3. Adicionar bibliotecas:
   - Filmes → `/media/movies`
   - Séries → `/media/tv`
4. Settings → Dashboard → Playback → Software (CPU) por ora

---

## Upgrade para Jellyfin 12

Jellyfin 12.0 (lançado 08/09/2026) é a renumeração do que seria "10.12" —
banco mais rápido para playlists/coleções, suporte nativo a livros/quadrinhos,
"Still watching?", scrub frame-a-frame, FFmpeg 8.1 e Modern UI como padrão.
`docker-compose.yml` já está fixado em `jellyfin/jellyfin:12.1`. **Upgrade
exige passos manuais — não é só trocar a tag e reiniciar:**

1. **Backup obrigatório** do volume de config antes de qualquer coisa:
   ```bash
   docker run --rm -v jellyfin_config:/from -v /mnt/backups:/to alpine \
     tar czf /to/jellyfin-config-$(date +%F).tar.gz -C /from .
   ```
2. **Checar a versão atual** (`Dashboard → About` ou `docker logs sb_jellyfin | grep -i version`):
   precisa estar em `10.10.7` ou `10.11.x` antes de pular pra 12. Se estiver
   mais antigo, atualizar primeiro para `10.10.7`.
3. **Remover plugins de terceiros** antes do upgrade — plugins compilados
   para 10.11 não carregam em 12.0/12.1 (precisam retarget pra .NET 10).
4. Checar se não há usernames duplicados diferindo só por maiúscula/minúscula
   (agora case-insensitive) — evita falha na migração do banco.
5. Subir a nova versão:
   ```bash
   git pull && docker compose pull && docker compose up -d
   ```
6. **Rescan completo da biblioteca é obrigatório** após o upgrade — a
   primeira varredura demora bem mais que o normal. Não parar o container
   durante a migração do banco.
7. Dar hard-refresh no client web (`Ctrl+Shift+R`) depois que a migração
   terminar.

---

## Seerr — pedidos de mídia

Sucessor unificado do Jellyseerr + Overseerr (`github.com/seerr-team/seerr`).
Deixa qualquer usuário pedir filme/série pela UI; ele fala com o Jellyfin
(biblioteca) e com Radarr/Sonarr (automação de download, LXC 10). Roda no
mesmo `docker-compose.yml` deste LXC, na mesma rede `media`.

- **Acesso:** `http://192.168.0.218:5055` / `https://seerr.joaopaulo.me`
- **Versão pinada:** `ghcr.io/seerr-team/seerr:v3.4.1` — nunca usar `:latest`,
  atualizar o pin manualmente no `docker-compose.yml` ao subir de versão.

### Setup inicial (UI)

1. Acessar `http://192.168.0.218:5055` e completar o wizard.
2. Conectar ao Jellyfin usando o nome do container na rede interna:
   `http://sb_jellyfin:8096`.
3. Conectar Radarr e Sonarr (LXC 10, `sb-arr`) via IP + API key de cada um:
   - Radarr: `http://192.168.0.219:7878`
   - Sonarr: `http://192.168.0.219:8989`
4. Gerar a API key do Seerr em `Settings → General` — usada no widget do
   Homepage (`HOMEPAGE_VAR_SEERR_API_KEY`).

### Cloudflare Access (passo manual, fora deste repo)

Seerr fica atrás de Cloudflare Access, mesmo padrão do Affine/Ryot — quem
não estiver autorizado nem chega na tela de login do Seerr. Isso é
configurado direto no painel do Cloudflare Zero Trust, não em arquivo
versionado neste repo:

1. Cloudflare Zero Trust → **Access → Applications** → Add an application
   → Self-hosted.
2. Domain: `seerr.joaopaulo.me`.
3. Policy: restringir por e-mail (ou grupo) aos usuários autorizados.
