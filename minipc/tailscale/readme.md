# Mini PC — Tailscale (acesso remoto)

> **IP Tailscale:** 100.105.155.54  
> **Hostname:** homalabzin

VPN mesh para acesso remoto ao homelab. Funciona atrás de CGNAT sem port forwarding. Expõe toda a rede `192.168.0.0/24` para dispositivos conectados na mesma conta Tailscale.

---

## Pré-requisito: IP forwarding

Necessário para o subnet routing (`192.168.0.0/24`) funcionar. Executar uma vez no host:

```bash
echo 'net.ipv4.ip_forward = 1' | sudo tee /etc/sysctl.d/99-tailscale.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
```

---

## Deploy

Instalado via **CasaOS App Store** (`http://192.168.0.12:8888`). O CasaOS gerencia o ciclo de vida do container — não substituir pelo compose manualmente.

O compose neste diretório é documentação de referência (com `TS_EXTRA_ARGS` adicionado).

**Web UI do Tailscale:** `http://192.168.0.12:5252`

---

## Aprovar subnet routing (uma vez)

Após o container subir com `--advertise-routes`, aprovar no painel:

1. Acessar [tailscale.com/admin/machines](https://tailscale.com/admin/machines)
2. Clicar em `homalabzin` → **Edit route settings**
3. Ativar `192.168.0.0/24`

---

## Verificação

```bash
# Status e dispositivos conectados
docker exec tailscale tailscale status

# Rotas anunciadas
docker exec tailscale tailscale ip -4

# Testar acesso à rede interna (do celular ou notebook fora de casa)
# ping 192.168.0.12   ← Mini PC
# ping 192.168.0.218  ← Jellyfin
# ping 192.168.0.219  ← Prowlarr
```

---

## Recriar container com volume persistente

O container atual não tem volume — se reiniciar, perde a autenticação. Para migrar:

```bash
# Parar container atual
docker stop tailscale && docker rm tailscale

# Subir com o compose (agora com volume persistente)
docker compose up -d

# Autenticar novamente se necessário
docker logs tailscale | grep "https://login"
```
