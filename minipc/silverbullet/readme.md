# Mini PC — SilverBullet

Leitor markdown de conveniência — acesso avulso ao vault do Obsidian no Mac, via Nextcloud Desktop Client.

## Setup

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
Hermes (LXC 2)
  ↓ (SSHFS via Tailscale)
notebook/Obsidian Vault (real)
  ↓ (LiveSync CouchDB)
Mini PC/Nextcloud ← (via Nextcloud Desktop Client no notebook)
  ↓ (volume mount)
SilverBullet
```

O Nextcloud Desktop Client roda no notebook em paralelo ao Obsidian LiveSync, sincronizando a mesma pasta do vault — sem requisito de write-back pro vault real.

## Notas

- SilverBullet está pronto pra uso de leitura/edição — não bloqueia o core do projeto
- Upgrade de versão pode variar o comportamento do plugin system — futuro upgrade não recomendado sem teste prévio
