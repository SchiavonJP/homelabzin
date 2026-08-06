# Mini PC — Vaultwarden (gerenciador de senhas)

> **Acesso público:** `https://vault.joaopaulo.me`  
> **Gerenciado por:** CasaOS App Store

Servidor Bitwarden auto-hospedado. Compatível com todos os clientes oficiais do Bitwarden (browser extension, iOS, Android, desktop). HTTPS via Cloudflare Tunnel é obrigatório para os apps mobile funcionarem.

---

## Instalação via CasaOS

1. CasaOS → App Store → buscar **Vaultwarden** → instalar
2. Anotar a porta que o CasaOS atribuiu (geralmente 8222 ou similar)
3. Acessar `http://192.168.0.12:<porta>` → criar conta

---

## Configurar HTTPS via Cloudflare Tunnel

Os apps mobile do Bitwarden **exigem HTTPS** — sem isso, a conexão é recusada.

```bash
# Substituir <tunnel-name> pelo nome do seu tunnel (ver: cloudflared tunnel list)
cloudflared tunnel route dns <tunnel-name> vault.joaopaulo.me
```

Adicionar ao `/etc/cloudflared/config.yml` no Mini PC (antes da linha `- service: http_status:404`):
```yaml
- hostname: vault.joaopaulo.me
  service: http://127.0.0.1:<porta-vaultwarden>
```

```bash
systemctl restart cloudflared
```

Verificar:
```bash
curl https://vault.joaopaulo.me/alive
```

---

## Admin token (opcional mas recomendado)

O painel de admin (`/admin`) permite gerenciar usuários e configurações avançadas. Para habilitar, configurar via CasaOS env vars:

```
ADMIN_TOKEN=<senha-forte>
```

Acesso: `https://vault.joaopaulo.me/admin`

Para gerar um token seguro:
```bash
openssl rand -base64 48
```

---

## Apps e extensões

| Cliente | Como configurar |
|---------|----------------|
| **Bitwarden** (iOS/Android) | Settings → Server URL → `https://vault.joaopaulo.me` |
| **Bitwarden** (Chrome/Firefox) | Settings → Server URL → `https://vault.joaopaulo.me` |
| **Bitwarden** (Desktop) | Settings → Server URL → `https://vault.joaopaulo.me` |

Criar conta pelo browser primeiro (`https://vault.joaopaulo.me`) antes de fazer login nos apps.

---

## Notas de segurança

- Por padrão, qualquer pessoa pode criar conta. Para fechar registros após criar sua conta:
  CasaOS env vars → `SIGNUPS_ALLOWED=false`
- Dados em `/DATA/AppData/vaultwarden` — incluir no backup
