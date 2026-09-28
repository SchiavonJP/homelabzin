# Notebook Pessoal — <hostname/IP LAN> (Tailscale: <IP 100.x.x.x>)

> **OS:** Linux
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

```bash
# SSH server
sudo systemctl enable --now ssh

# Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4   # IP usado pelo LXC 2 no SSHFS

# Path real do vault (confirmar antes de liberar acesso)
cat ~/.config/obsidian/obsidian.json
```

Chave dedicada para o mount do Hermes (pública vem do LXC 2, ver
`LXC_2_hermes_mcp/readme.md`), adicionada em `~/.ssh/authorized_keys` com
`restrict,sftp` — sem acesso a shell, só ao filesystem do vault.

## Verificação

```bash
tailscale status            # confere que o LXC 2 aparece como peer
sudo systemctl status ssh   # sshd ativo
```

## Notas

- Este notebook precisa estar **ligado** e com o **Obsidian aberto** para o LiveSync
  notar e propagar arquivos escritos externamente (pelo Hermes) — não é uma ponte
  24/7, ver limitação no plano principal do vault sync (`plan.md`).
- Não confundir com o vault "notinhas" (`~/Documents/obsidian/notinhas` no Mac
  pessoal usado no Claude Code) — esse ficou vazio/nunca fetchado e não é usado.
- IP LAN, IP Tailscale e path exato do vault ainda são placeholders acima —
  preencher depois de rodar o setup neste notebook (pendente: autorização do
  Tailscale + confirmação do path do vault).
