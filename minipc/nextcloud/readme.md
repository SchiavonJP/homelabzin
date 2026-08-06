# Mini PC — Nextcloud (Google Drive replacement)

> **Acesso LAN:** `http://192.168.0.12:7580`  
> **Gerenciado por:** CasaOS App Store

Substitui o Google Drive para armazenamento de arquivos pessoais, sincronização e compartilhamento.

---

## Stack em execução

| Container | Imagem | Papel |
|-----------|--------|-------|
| `nextcloud` | big-bear-nextcloud:0.0.12 | Aplicação principal |
| `nextcloud-cron` | big-bear-nextcloud:34.0.1 | Cron jobs |
| `db-nextcloud` | postgres:14.2 | Banco de dados |
| `redis-nextcloud` | redis:6.2.20 | Cache |

Dados em `/DATA/AppData/nextcloud` (gerenciado pelo CasaOS).

---

## Apps mobile

- **iOS/Android:** buscar "Nextcloud" na App Store / Play Store
- Server: `http://192.168.0.12:7580` (LAN) ou via Tailscale

---

## Acesso público (opcional)

Para sincronizar fora de casa sem Tailscale, expor via Cloudflare Tunnel:

```bash
# No Mini PC
cloudflared tunnel route dns <tunnel-name> cloud.joaopaulo.me
```

Adicionar ao `/etc/cloudflared/config.yml`:
```yaml
- hostname: cloud.joaopaulo.me
  service: http://127.0.0.1:7580
```

```bash
systemctl restart cloudflared
```

---

## Notas

- Não alterar `db-nextcloud` ou `redis-nextcloud` diretamente — gerenciados pelo compose do CasaOS
- Backup dos dados: `/DATA/AppData/nextcloud` deve ser incluído no backup do Mini PC
