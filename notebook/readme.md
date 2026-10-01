# Notebook Pessoal — schiva-g77588 (Tailscale: 100.80.3.58)

> **OS:** Arch Linux
> **Usuário:** schiva
> **Vault real:** `/home/schiva/Documentos/Obsidian Vault`
> **Papel:** máquina de uso diário — dono do vault real do Obsidian (arquivos .md
> que o LiveSync sincroniza)

## Componentes / Arquitetura

| Componente | Papel |
|---|---|
| Obsidian + plugin Self-hosted LiveSync | Cliente do vault — já configurado, aponta pro CouchDB do Mini PC (porta 5984, `obsidian.joaopaulo.me`). Não recriar. |
| OpenSSH server (sshd) | Permite o LXC 2 montar a pasta do vault via SSHFS |
| Tailscale | Cliente comum da tailnet (não subnet router — isso é papel do Mini PC) — mantém o notebook alcançável pelo LXC 2 mesmo fora da LAN de casa |

Fluxo: `Hermes (LXC 2) --SSHFS via Tailscale--> pasta local do vault (aqui) <--LiveSync--> CouchDB (Mini PC) <--LiveSync--> celular`

## Pré-requisitos / instalação

Arch Linux — o serviço se chama `sshd`, não `ssh`, e pode precisar instalar o
pacote primeiro:

```bash
# SSH server
sudo pacman -S --needed openssh
sudo systemctl enable --now sshd

# Tailscale (pacman)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4   # 100.80.3.58 — IP usado pelo LXC 2 no SSHFS

# Path real do vault (confirmar antes de liberar acesso)
cat ~/.config/obsidian/obsidian.json
```

Chave dedicada para o mount do Hermes (pública vem do LXC 2, ver
`LXC_2_hermes_mcp/readme.md`), adicionada em `~/.ssh/authorized_keys`:

```
restrict,command="internal-sftp" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFM7S7i068wVK6TceWDwqID0Pr0Rrjwlo9MSm7oBXfry hermes-vault-mount@sb-hermes
```

**Atenção:** `sftp` sozinho como option keyword **não existe** no formato do
`authorized_keys` do OpenSSH (tentamos isso primeiro e a linha foi silenciosamente
ignorada — sshd caiu direto pra auth por senha sem nem tentar a chave). A forma
correta de restringir a chave a SFTP é `restrict,command="internal-sftp"`.

## Verificação

```bash
tailscale status             # confere que o LXC 2 aparece como peer
sudo systemctl status sshd   # sshd ativo
```

## Notas

- Este notebook precisa estar **ligado** e com o **Obsidian aberto** para o LiveSync
  notar e propagar arquivos escritos externamente (pelo Hermes) — não é uma ponte
  24/7, ver limitação no plano principal do vault sync (`plan.md`).
- Não confundir com o vault "notinhas" (`~/Documents/obsidian/notinhas` no Mac
  pessoal usado no Claude Code) — esse ficou vazio/nunca fetchado e não é usado.
- Verificado end-to-end em 2026-09-28: Hermes escreveu uma nota de teste via
  `POST /vault/notes` e ela apareceu neste path real (confirmado via SFTP
  separado), depois removida.
- O mount no lado do LXC 2 usa `/etc/fstab` com `fuse.sshfs` + `nofail` (não
  `x-systemd.automount` — unidades automount não são suportadas dentro desse
  container LXC; o mount acontece via unidade `.mount` normal no boot, sem
  travar caso este notebook esteja offline).
