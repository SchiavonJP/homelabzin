# Logseq — Sync via Nextcloud WebDAV

Nenhum container extra necessário. O Nextcloud (porta 7580) já expõe WebDAV.

---

## Mobile (iOS / Android) — aponta direto, sem instalar nada

Logseq Mobile tem WebDAV nativo:

Settings → Sync → **WebDAV**
- URL: `http://192.168.0.12:7580/remote.php/dav/files/SEU_USER/Logseq/`
- Usuário / Senha: suas credenciais do Nextcloud

Criar a pasta `Logseq/` no Nextcloud antes (via UI ou curl):

```bash
curl -u SEU_USER:SENHA -X MKCOL \
  http://192.168.0.12:7580/remote.php/dav/files/SEU_USER/Logseq/
```

---

## Desktop — requer montar WebDAV como pasta local

Logseq Desktop trabalha com pastas locais, não tem WebDAV nativo.
É preciso montar o Nextcloud como uma pasta — sem instalar nada extra:

### Mac (nativo)
Finder → **Ir → Conectar ao servidor**
```
http://192.168.0.12:7580/remote.php/dav/files/SEU_USER/
```
A pasta fica disponível em `/Volumes/SEU_USER/`. Aponte o Logseq para `/Volumes/SEU_USER/Logseq/`.

> Limitação: a montagem some após reiniciar o Mac. Para persistir, adicione ao Login Items ou use o Nextcloud Desktop Client.

### Linux
```bash
sudo apt install davfs2
sudo mount -t davfs http://192.168.0.12:7580/remote.php/dav/files/SEU_USER/ /mnt/nextcloud
```

### Windows
Explorer → **Adicionar local de rede** → URL do WebDAV acima.

### Alternativa: Nextcloud Desktop Client
Instale o cliente Nextcloud — ele faz o sync em background de forma transparente,
criando uma pasta local `~/Nextcloud/` que sempre está sincronizada.
Aponte o Logseq para `~/Nextcloud/Logseq/`.

---

## Acesso externo (fora de casa)

Use o IP Tailscale do Mini PC no lugar de `192.168.0.12` — funciona em mobile e desktop.
