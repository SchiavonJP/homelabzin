# Mini PC — AdGuard Home (DNS ad-blocker)

> **Acesso LAN:** `http://192.168.0.12:3001`  
> **Gerenciado por:** CasaOS App Store

Bloqueia anúncios e trackers na rede inteira via DNS. Levíssimo (~50 MB RAM). Configurado como DNS do Tailscale → ad-blocking em todos os dispositivos mesmo fora de casa.

---

## Instalação via CasaOS

1. CasaOS → App Store → buscar **AdGuard Home** → instalar
2. Acessar `http://192.168.0.12:3000` (wizard de setup inicial)
3. Seguir o wizard — definir usuário/senha admin
4. Após o wizard, UI fica em `http://192.168.0.12:3001`

---

## Conflito porta 53 (se ocorrer)

Se o AdGuard não subir na porta 53, o `systemd-resolved` do host pode estar ocupando:

```bash
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved
# Garantir DNS funcional no host
echo "nameserver 1.1.1.1" | sudo tee /etc/resolv.conf
```

Reiniciar o container AdGuard após liberar a porta.

---

## Configurar como DNS da rede local

No roteador (192.168.0.1), configurar DNS primário para `192.168.0.12`. Todos os dispositivos da rede passam a usar o AdGuard automaticamente.

---

## Configurar como DNS do Tailscale (ad-blocking remoto)

Para bloquear anúncios em todos os dispositivos Tailscale, mesmo fora de casa:

1. Acessar [tailscale.com/admin/dns](https://tailscale.com/admin/dns)
2. **Add nameserver** → Custom → `100.105.155.54` (IP Tailscale do Mini PC)
3. Marcar **Override local DNS**

Agora celular, notebook e qualquer dispositivo Tailscale usam o AdGuard como DNS.

---

## Listas de bloqueio recomendadas

Em AdGuard → Filters → DNS blocklists → Add:
- `https://adguardteam.github.io/HostlistsRegistry/assets/filter_1.txt` (AdGuard DNS filter)
- `https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts` (StevenBlack)

---

## Verificação

```bash
# Testar resolução via AdGuard
nslookup google.com 192.168.0.12

# Testar bloqueio (deve retornar 0.0.0.0)
nslookup doubleclick.net 192.168.0.12
```
