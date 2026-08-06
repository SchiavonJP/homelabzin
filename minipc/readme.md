# Mini PC — 192.168.0.12

> **OS:** CasaOS  
> **Acesso:** `http://192.168.0.12:8888`  
> **Papel:** Storage 24/7 + serviços leves

O Mini PC fica sempre ligado. Ele é o **dono da biblioteca de mídia** e serve o conteúdo para os LXCs do Proxmox via NFS.

---

## Serviços em execução

| Container | Imagem | Porta | Role |
|-----------|--------|-------|------|
| `traefik` | traefik:v3.6 | 80, 443, 8088 | Reverse proxy local |
| `cloudflared` | cloudflared-web | — | Cloudflare Tunnel |
| `obsidian-livesync` | couchdb:3.5.0 | 5984 | Vault sync — não tocar |
| `nextcloud` | big-bear-nextcloud | 7580 | File storage / cloud |
| `nextcloud-cron` | big-bear-nextcloud | — | Cron do Nextcloud |
| `db-nextcloud` | postgres:14.2 | — | Banco do Nextcloud |
| `redis-nextcloud` | redis:6.2.20 | — | Cache do Nextcloud |
| `code-server` | code-server:4.106.3 | 8082 | VS Code no browser |
| `minipc_navidrome` | navidrome:latest | 4533 | Streaming de música |
| `tailscale` | tailscale:v1.90.8 | 5252 (web UI) | VPN — acesso remoto à rede 192.168.0.0/24 |

---

## Storage

Estrutura de diretórios no Mini PC (criar se não existir):

```bash
mkdir -p /storage/{music,movies,tv,downloads}
```

| Diretório | Conteúdo |
|-----------|----------|
| `/storage/music` | Biblioteca musical (Navidrome + Lidarr) |
| `/storage/movies` | Filmes (Radarr + Jellyfin) |
| `/storage/tv` | Séries (Sonarr + Jellyfin) |
| `/storage/downloads` | Landing zone do qBittorrent |

---

## NFS — via Docker

O NFS roda no container `minipc_nfs` (imagem `erichough/nfs-server`).

As portas 111 e 2049 podem estar ocupadas pelo `nfs-kernel-server` / `rpcbind` nativos — o setup remove esses serviços antes de subir o container.

### Setup (executar uma vez como root)

```bash
bash minipc/nfs/setup-nfs.sh
```

O script:
1. Para e desinstala `nfs-kernel-server` + `rpcbind` nativos
2. Cria os diretórios de storage
3. Sobe o container Docker

### Verificação

```bash
# No Mini PC
docker ps | grep minipc_nfs
showmount -e localhost

# De qualquer LXC no Proxmox
showmount -e 192.168.0.12
```

Saída esperada:
```
Export list for 192.168.0.12:
/storage  192.168.0.0/24
```

### Mount nos LXCs do Proxmox

Adicionar ao `/etc/fstab` de cada LXC que precisa da biblioteca:

```
192.168.0.12:/storage /mnt/media nfs defaults,_netdev,nofail,soft,timeo=30 0 0
```

Depois:

```bash
mkdir -p /mnt/media
mount -a
ls /mnt/media/  # deve mostrar music, movies, tv, downloads
```

---

## Navidrome

Streaming de música disponível 24/7, independente do Proxmox.

### Deploy

```bash
docker compose -f minipc/navidrome/docker-compose.yml up -d
```

### Acesso

- LAN: `http://192.168.0.12:4533`
- Público (opcional): adicionar rota no Traefik local → `music.joaopaulo.me`

### Primeiro acesso

Na primeira visita, criar o usuário admin. Navidrome faz scan automático da biblioteca a cada 1h. Para forçar rescan:

```bash
docker exec minipc_navidrome navidrome scan --full
```

---

## Obsidian LiveSync

Já em produção — **não tocar**. O CouchDB roda no container `obsidian-livesync` na porta 5984. Não reiniciar, não alterar credenciais.
