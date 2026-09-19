# LXC 13 — Camera (motionEye)

> **Hostname LXC:** sb-camera
> **VMID:** 114
> **IP:** 192.168.0.222
> **Porta:** 8765
> **URL pública:** https://camera.joaopaulo.me (pendente — ver seção Traefik)

Webcam USB conectada diretamente no host Proxmox, usada pra monitorar o
cachorro remotamente. Roda [motionEye](https://github.com/motioneye-project/motioneye)
(imagem mantida `motioneyeproject/motioneye` — **não** `ccrisan/motioneye`,
fork original sem atualização desde 2021): detecção de movimento, gravação de
clipes e live view via navegador. Sem notificação push por ora — só UI.

Frigate (detecção de objeto real via IA, alerta só quando reconhece
"cachorro") foi avaliado e descartado por ora: a GPU do Apollo (LXC 8) já
está com ~11GB/12GB de VRAM ocupados, sobrando pouca folga pra um detector, e
detecção via CPU é lenta demais pra compensar o ganho de precisão numa única
câmera. Upgrade path se motionEye gerar falso-positivo demais.

---

## Hardware alocado

| Recurso | Valor |
|---------|-------|
| CPU | 2 cores |
| RAM | 1024 MB |
| Swap | 512 MB |
| Disco | 20 GB |
| Câmera | Webcam USB (V4L2, passthrough) — Aveo Technology Corp. USB2.0 Camera (`1871:0142`) |

---

## Pré-requisitos no host Proxmox

### 1. Identificar a webcam

```bash
ls -la /dev/v4l/by-id/
# usb-AVEO_Technology_Corp._USB2.0_Camera-video-index0 -> ../../video0  (nó de captura)
# usb-AVEO_Technology_Corp._USB2.0_Camera-video-index1 -> ../../video1  (metadata, não usar)

lsusb | grep -i aveo
# Bus 003 Device 002: ID 1871:0142 Aveo Technology Corp. USB2.0 Camera
```

Sempre usar o symlink `-video-index0` do by-id — é o nó de captura real, não
o de metadata/ISOC que a câmera também expõe.

### 2. Criar regra udev (device estável entre reboots/replug)

`/etc/udev/rules.d/99-webcam-lxc.rules`:
```
SUBSYSTEM=="video4linux", KERNEL=="video0", ATTRS{idVendor}=="1871", ATTRS{idProduct}=="0142", OWNER="100000", GROUP="100044", MODE="0660", SYMLINK+="video-dogcam"
```

```bash
udevadm control --reload-rules
udevadm trigger --subsystem-match=video4linux
```

UID/GID `100000`/`100044` = mapeamento padrão de container **unprivileged**
(root/video dentro do LXC → 100000/100044 no host). Sem isso o device fica
inacessível pro container mesmo com o bind mount certo.

### 3. Criar o container

```bash
pct create 114 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst \
  --hostname sb-camera \
  --memory 1024 --swap 512 --cores 2 \
  --rootfs local-lvm:20 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.0.222/24,gw=192.168.0.1 \
  --unprivileged 1 \
  --features keyctl=1,nesting=1 \
  --onboot 1
```

Diferente do GPU passthrough do LXC 8 (Apollo, que usa `--unprivileged 0`),
webcam V4L2 funciona em container **unprivileged** — confirmado em produção
neste LXC. Só precisa das cgroup allow rules + mount entries abaixo.

### 4. Adicionar passthrough ao `/etc/pve/lxc/114.conf`

```ini
# USB webcam passthrough — Aveo USB2.0 Camera (V4L2, major 81) + underlying USB node
lxc.cgroup2.devices.allow: c 81:* rwm
lxc.cgroup2.devices.allow: c 189:* rwm
lxc.mount.entry: /dev/video-dogcam dev/video0 none bind,optional,create=file
lxc.mount.entry: /dev/bus/usb/003/002 dev/bus/usb/003/002 none bind,optional,create=file
```

> O bus/device USB (`003/002`) pode mudar se a câmera for replugada em outra
> porta física — reconferir com `lsusb` se o container parar de ver a câmera
> depois de mexer no cabo USB.

```bash
pct start 114
pct exec 114 -- ls -la /dev/video0   # confirmar visível dentro do LXC
```

### 5. Bootstrap (Docker + acesso)

```bash
pct exec 114 -- bash -c "apt-get update -qq && apt-get install -y curl && curl -fsSL https://get.docker.com | sh"
```

> **Acesso SSH:** a injeção automática de chave via `tee` em
> `authorized_keys` é bloqueada por política de segurança de endpoint neste
> ambiente (padrão comum de "backdoor" detectado por EDR). Configure acesso
> manualmente — `pct exec 114 -- passwd root` (senha) ou copie a chave pública
> por outro canal — ou opere via `pct exec 114 -- <comando>` direto do host
> Proxmox, sem precisar de SSH pro LXC.

---

## Deploy

Arquivos deste diretório (`docker-compose.yml`, `.env.example`) copiados pro
LXC via `pct push` (sem depender de `git clone` + chave SSH):

```bash
# No host Proxmox, a partir do checkout local do repo
pct push 114 LXC_13_camera/docker-compose.yml /opt/camera/docker-compose.yml
pct exec 114 -- mkdir -p /opt/camera
pct push 114 LXC_13_camera/docker-compose.yml /opt/camera/docker-compose.yml
pct exec 114 -- bash -c "cd /opt/camera && docker compose up -d"
```

(Alternativa de longo prazo, uma vez resolvido o acesso SSH/GitHub: sparse
checkout deste repo dentro do LXC, mesmo padrão dos outros LXCs — ver
bootstrap em `HOMELAB.md`.)

Configurar na UI (`http://192.168.0.222:8765`, login padrão `admin`/sem
senha — **trocar a senha no primeiro acesso**):
- Adicionar câmera apontando pra `/dev/video0`.
- "Event Gap" (~30s) em Motion Detection, pra evitar clipes fragmentados.
- Retenção de gravações (auto-delete por idade/espaço) — importante pra não
  estourar os 20GB de disco do LXC, já que não há gravação contínua 24/7, só
  disparada por movimento.

> **Notificação push (futuro, não incluído agora):** motionEye suporta hooks
> `on_motion_detected`/`on_movie_end` (shell command) — se decidir ativar
> depois, basta apontar um `curl` desses hooks pro ntfy que já roda no LXC 3
> (Odysseus), sem mudar mais nada da stack.

---

## Traefik / Cloudflare Access

Rota já adicionada em `LXC_1_traefik/dynamic/services.yml`
(`camera.joaopaulo.me` → `http://192.168.0.222:8765`), **mas o LXC 1
(Traefik) não está rodando no host no momento deste deploy** — não aparece em
`pct list` nem em `qm list`, e `192.168.0.212` não responde. A rota fica
pronta pra quando o Traefik for restaurado; até lá, acesso é só via IP local
(`http://192.168.0.222:8765`).

Quando o Traefik voltar, seguir o mesmo padrão de Affine/Windmill/Dify
(`LXC_12_personal_hub/affine/README.md`): Zero Trust → Access → Applications
→ criar app pra `camera.joaopaulo.me`, policy restringindo ao seu email —
recomendado (não opcional) porque é feed de câmera de dentro de casa, mais
sensível que os outros serviços do repo, e motionEye só tem auth simples
usuário/senha sem MFA.

---

## Verificação

```bash
# 1. Host vê a webcam
ls /dev/video*; ls -la /dev/v4l/by-id/

# 2. LXC vê o device
pct exec 114 -- ls -la /dev/video0

# 3. Container vê o device
pct exec 114 -- docker exec sb_camera ls -la /dev/video0

# 4. Serviço respondendo
pct exec 114 -- docker compose -f /opt/camera/docker-compose.yml ps
curl http://192.168.0.222:8765/

# 5. UI mostra live feed
# → http://192.168.0.222:8765
```

---

## Troubleshooting

| Problema | Causa provável | Solução |
|----------|---------------|---------|
| `/dev/video0` não aparece no LXC | Passthrough não configurado ou udev rule não recarregada | Reconferir `/etc/pve/lxc/114.conf` e rodar `udevadm trigger` no host |
| Device aparece no LXC mas container não abre | `devices:` faltando no compose, ou container rodou antes do device existir | Conferir `devices: ["/dev/video0:/dev/video0"]` no compose e reiniciar o container |
| `Permission denied` ao abrir `/dev/video0` | Ownership do device no host não mapeado pro UID do unprivileged LXC | Reconferir `OWNER=100000 GROUP=100044` na regra udev |
| Câmera some depois de replugar o cabo USB | `/dev/videoN` reindexado, ou bus/device USB mudou de porta | O symlink by-id/udev deve resolver o `/dev/videoN`; reconferir `lsusb` pro bus/device se usar o mount entry de `/dev/bus/usb/*` |
| `camera.joaopaulo.me` não resolve | Traefik (LXC 1) não está rodando no host | Ver seção Traefik acima — acessar via IP local até restaurar |
| Não consigo SSH no LXC | Bloqueio de política de segurança do endpoint (EDR) na injeção automática de chave | Configurar acesso manualmente ou operar via `pct exec` do host Proxmox |
