# Mini PC — Immich (Google Photos replacement)

> **Acesso LAN:** `http://192.168.0.12:2283`  
> **Acesso público:** `https://photos.joaopaulo.me`  
> **Gerenciado por:** CasaOS App Store

Substitui o Google Photos — backup automático de fotos e vídeos do celular, álbuns, linha do tempo. ML worker desabilitado para poupar RAM no Celeron 4020 com 4 GB.

---

## Instalação via CasaOS

1. CasaOS (`http://192.168.0.12:8888`) → App Store → buscar **Immich** → instalar
2. Após instalar, **desabilitar o ML worker** para economizar ~1.5 GB RAM:
   - No CasaOS, editar o app Immich → remover ou comentar o serviço `immich-machine-learning`
   - Ou adicionar variável de ambiente: `DISABLE_MACHINE_LEARNING=true`
3. Acessar `http://192.168.0.12:2283` → criar conta admin

---

## Storage

Por padrão, o CasaOS salva em `/DATA/AppData/immich/library`. Para usar o disco externo:

No CasaOS, editar o volume do container:
```
/DATA/AppData/immich/library → /storage/photos
```

Criar o diretório antes:
```bash
mkdir -p /storage/photos
```

---

## Acesso público (necessário para app mobile fora de casa)

```bash
# Criar DNS record
cloudflared tunnel route dns <tunnel-name> photos.joaopaulo.me
```

Adicionar ao `/etc/cloudflared/config.yml`:
```yaml
- hostname: photos.joaopaulo.me
  service: http://127.0.0.1:2283
```

```bash
systemctl restart cloudflared
```

---

## App mobile

1. Instalar **Immich** (iOS/Android)
2. Server URL: `https://photos.joaopaulo.me`
3. Login com a conta criada no primeiro acesso
4. Settings → Backup → ativar backup automático (recomendado: Wi-Fi only)

---

## O que funciona sem ML

- Backup automático de fotos e vídeos ✅
- Álbuns e compartilhamento ✅
- Linha do tempo ✅
- Busca por data/lugar ✅
- Reconhecimento facial ❌ (requer ML worker)
- Busca por objetos ("cachorro", "praia") ❌ (requer ML worker)
