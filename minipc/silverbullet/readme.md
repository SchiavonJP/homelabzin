# Mini PC — SilverBullet

> **Current Xereta integration (2026-11-05):** Xereta reads the Mini PC's SilverBullet `space/` vault. SilverBullet mounts Nextcloud's vault directory; Nextcloud Desktop on the notebook connects that directory to the Obsidian vault. CouchDB/LiveSync separately connects Obsidian devices. See [Xereta deployment and gates](../../apps/xereta/README.md).

## Current shared vault

SilverBullet is the browser editor for the Nextcloud-backed vault. Runtime mounts verified on 2026-11-05:

- Nextcloud: `/DATA/AppData/big-bear-nextcloud/html` → `/var/www/html`.
- SilverBullet: `/DATA/AppData/big-bear-nextcloud/html/data/schiva/files/Vault` → `/data/space`.
- SilverBullet configuration/plugins: `/DATA/AppData/silverbullet-xereta/data` → `/data`.

Xereta reads notes under `space/` from the Mini PC; it no longer reads the notebook's SSHFS mount for this integration. Obsidian synchronization still requires the notebook's Nextcloud Desktop client. SilverBullet does not directly replicate CouchDB.

- Internal endpoint: `http://192.168.0.12:3011`; public endpoint: `https://silverbullet.joaopaulo.me`.
- Observed release: `2.11.1-0-g1340f736-2026-09-22T15-15-43Z`.
- Files API: `GET /.fs` and `GET /.fs/<encoded-path>`, with SHA256 ETags on GET.
- Live create/readback/conditional-update/stale-update gate passed on a disposable file; the probe removed its file afterward.
- Xereta publishes individual files under `space/_AgentKnowledge/Perguntas/` and `Conhecimento/`, a small `Index.md`, and dedicated checkbox sync tests. The old Inbox is preserved as history. Original notes and source synchronization remain unchanged.
- The owner-guided Obsidian roundtrip passed on November 5 locally (`2026-11-06T00:40:29Z`). The notebook-offline digest and reconnection test also passed: all 14 checked files matched after Nextcloud resumed, including the offline receipt, review pages and original notes. See the [offline evidence](../../apps/xereta/evidence/2026-11-06-notebook-offline.json).

Installed UI extensions include TreeView, Silversearch, PDF Viewer, Table Sorting and Filtering, Floating Journal Calendar, and Excalidraw. The Excalidraw library uses its previously qualified pinned revision; do not replace it with an unverified main-branch manifest.

## Nextcloud indexing repair — 2026-11-05

SilverBullet previously wrote as root and bypassed Nextcloud's file index. A targeted ownership repair and `occ files:scan` made `Trabaio.md` match the notebook and delivered all 10 generated review files. This establishes the actual Nextcloud intermediary; the earlier description of direct LiveSync synchronization was incorrect.

- SilverBullet now uses `PUID=33`, `PGID=33`, matching Nextcloud's `www-data`. Its existing image was reused without pulling an upgrade.
- All 13 existing configuration/plugin files were copied to persistent `/data` storage and verified by SHA256 before/after recreation. The shared vault mount is retained.
- CasaOS Compose file: `/var/lib/casaos/apps/zen_link/docker-compose.yml`. Keep both mounts and the UID/GID settings when editing CasaOS settings.
- [nextcloud-vault-scan.sh](nextcloud-vault-scan.sh) is installed as `/home/homelabzin/.local/bin/xereta-nextcloud-vault-scan`.
- A marked entry in `homelabzin`'s crontab runs it every minute. It scans only `schiva/files/Vault` under `flock`, as `www-data`, preserving other cron entries.
- Private last-run output: `/home/homelabzin/.local/state/xereta-nextcloud-sync/last-scan.log`. The file is replaced on each scan to bound log size. Expect up to one minute plus client download time for server edits.
- Mini PC backups of affected notes, application configuration/plugins, Compose and the prior crontab: `/home/homelabzin/.local/state/xereta-sync-repair/20261105T234605Z/` (private). The notebook's original note was separately preserved on Hermes under `/root/xereta/sync-repair/`.

Manual scan: `/home/homelabzin/.local/bin/xereta-nextcloud-vault-scan`. To disable periodic scanning, remove only the `xereta-nextcloud-vault-sync` marked crontab block. Do not reset CouchDB or force LiveSync replication to repair this path.

The owner-guided Obsidian roundtrip passed: the first check reached Xereta, its reply reached the notebook with an identical SHA256, and the owner's second check reached Xereta and completed the test. Nextcloud Desktop was found paused during the test and had to be resumed. See the [recorded evidence](../../apps/xereta/evidence/2026-11-05-nextcloud-sync-repair.json). Xereta's small nightly pilot is enabled at 03:00 America/Sao_Paulo for the three approved notes and owner feedback, starting November 7; see [activation evidence](../../apps/xereta/evidence/2026-11-06-nightly-pilot.json). The always-on server can read its local copy while the notebook is off; delivering new edits to Obsidian devices still depends on the notebook's client.

## Historical setup

The following records the earlier image and root-user configuration. The vault mount remains current; use the UID/GID and additional persistent mount above for the repaired deployment.

### Setup

**Imagem:** `ghcr.io/silverbulletmd/silverbullet:2.10.7`

**Volume:** `/DATA/AppData/big-bear-nextcloud/html/data/schiva/files/Vault:/data/space`

**Port:** 3011 (exposto via Traefik em `https://silverbullet.joaopaulo.me`)

```yaml
version: '3.8'

services:
  silverbullet:
    image: ghcr.io/silverbulletmd/silverbullet:2.10.7
    container_name: minipc_silverbullet
    restart: unless-stopped
    ports:
      - "3011:3000"
    volumes:
      - /DATA/AppData/big-bear-nextcloud/html/data/schiva/files/Vault:/data/space
    environment:
      PUID: "0"
      PGID: "0"
    user: "0:0"
    deploy:
      resources:
        limits:
          memory: 512m
```

## Status

✅ **Funcional** — leitura/edição de notas, navegação, pesquisa.

⚠️ **Limitação conhecida** — plugin system quebrado (Deno sandbox crash ao tentar recarregar plugins). Testado em versões 2.10.7 e 2.11.x sem sucesso. **Aceito como limitação estrutural** — o objetivo principal (ler o vault) funciona.

## Acesso

```
http://192.168.0.12:3011     (LAN local)
https://silverbullet.joaopaulo.me   (externo, via Traefik)
```

## Fluxo de sincronização

```
Obsidian no celular ←→ CouchDB / LiveSync ←→ Obsidian no notebook
                                              ↕ Nextcloud Desktop
                                     Nextcloud no Mini PC
                                              ↕ diretório compartilhado + occ scan
                                     SilverBullet ←→ Xereta
```

O Nextcloud Desktop Client roda no notebook em paralelo ao Obsidian LiveSync, sincronizando a mesma pasta do vault em ambos os sentidos. A leitura SSHFS do notebook foi usada no piloto anterior; não é a fonte atual do Xereta.

## Notas

- SilverBullet está pronto pra uso de leitura/edição — não bloqueia o core do projeto
- Upgrade de versão pode variar o comportamento do plugin system — futuro upgrade não recomendado sem teste prévio
