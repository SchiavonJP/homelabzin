# LXC 4 — AI Router

LiteLLM · endpoint único OpenAI-compatível para toda a stack

## Specs recomendadas do LXC

```
Hostname:   sb-litellm
Password:   (define uma senha root)
Template:   debian-12 (a que já baixaste)

CPU:        2 cores
RAM:        2048 MB  (2GB — suficiente para Postgres + Redis + FalkorDB)
Swap:       512 MB
Disk:       10 GB    (em qualquer storage que tenhas disponível)

Network:    vmbr0, DHCP  (ou IP fixo se preferires)
DNS:        deixa herdar do host

Name: eth0
Bridge: vmbr0
IPv4: Static
IPv4/CIDR: 192.168.0.210/24
Gateway: 192.168.0.1
```

**Três coisas importantes antes de subir:**

1. **IP do Mac M1 no `config.yaml`** — substitui `<IP_MAC_M1>` pelo IP real do teu Mac na rede local. E no Mac, o Ollama precisa estar exposto na rede, não só em localhost:
```bash
OLLAMA_HOST=0.0.0.0 ollama serve
```

2. **Database do LiteLLM** — o `init/01_databases.sql` do LXC 5 não criou um database `litellm`. Podes usar o `secondbrain` que já existe, ou adicionar no LXC 5:
```bash
docker exec -it sb_postgres psql -U secondbrain -c "CREATE DATABASE litellm; GRANT ALL PRIVILEGES ON DATABASE litellm TO secondbrain;"
```

3. **Versão fixada em `main-stable`** — evita as versões 1.82.7 e 1.82.8 que tiveram o incidente de segurança em março.

**Fallbacks automáticos** — se o Mac M1 estiver desligado ou lento, o LiteLLM cai automaticamente para OpenRouter sem que o Hermes ou Odysseus percebam. Isto é o principal valor do router.

**UI de administração** em `http://<IP_LXC4>:4000/ui` — dá para ver custo por chamada, logs e gerir virtual keys por serviço.

## Pré-requisitos

```bash
# LXC Debian 12 com nesting=1
# features: keyctl=1,nesting=1  no /etc/pve/lxc/<id>.conf

apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
```

## Deploy via Git

```bash
# SSH access (run once from Proxmox host)
pct exec <VMID> -- mkdir -p /root/.ssh
cat ~/.ssh/id_ed25519.pub | pct exec <VMID> -- tee /root/.ssh/authorized_keys
pct exec <VMID> -- chmod 700 /root/.ssh
pct exec <VMID> -- chmod 600 /root/.ssh/authorized_keys

# Clone only this folder (run on LXC 4)
git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/second-brain-automation.git
cd second-brain-automation
git sparse-checkout init --cone
git sparse-checkout set LXC_4_litellm
git checkout main
cd LXC_4_litellm
```

## Setup

```bash
# 1. Editar variáveis
cp .env.example .env
nano .env   # fill in LITELLM_MASTER_KEY, LITELLM_SALT_KEY, OPENROUTER_API_KEY, passwords

# 2. Substituir <IP_MAC_M1> no config.yaml pelo IP real do Mac
nano config.yaml

# 3. Subir
docker compose up -d

# 4. Verificar
docker compose ps
curl http://localhost:4000/health
```

### Pull updates

```bash
cd ~/second-brain-automation && git pull
cd LXC_4_litellm && docker compose up -d
```

## Testar roteamento

```bash
# Testar modelo local (Mac M1)
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-troca_esta_chave_master" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.1-8b",
    "messages": [{"role": "user", "content": "responde só: ok"}]
  }'

# Testar modelo cloud (OpenRouter)
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-troca_esta_chave_master" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet",
    "messages": [{"role": "user", "content": "responde só: ok"}]
  }'
```

## UI de administração

```
http://<IP_LXC4>:4000/ui
login: admin / <LITELLM_MASTER_KEY>
```

Mostra: modelos disponíveis, custo por chamada, logs, virtual keys.

## Ollama no Mac M1

O Mac M1 precisa ter o Ollama acessível na rede local:

```bash
# No Mac M1 — expor Ollama na rede (não só localhost)
launchctl setenv OLLAMA_HOST "0.0.0.0"
# ou via variável de ambiente antes de iniciar o Ollama
OLLAMA_HOST=0.0.0.0 ollama serve

# Verificar modelos disponíveis
ollama list
```

## Modelos pré-configurados

| Alias         | Backend     | Uso                          |
|---------------|-------------|------------------------------|
| llama3.1-8b   | Mac M1      | Tarefas rápidas e leves      |
| qwen2.5-coder | Mac M1      | Completions de código        |
| hermes-local  | Mac M1      | Síntese e memória leve       |
| claude-sonnet | OpenRouter  | Raciocínio e síntese profunda|
| gpt-4o        | OpenRouter  | Fallback geral               |
| deepseek-r1   | OpenRouter  | Análise longa de código      |
| auto-light    | → Mac M1    | Alias automático leve        |
| auto-heavy    | → OpenRouter| Alias automático pesado      |

## Fallbacks configurados

Se o Mac M1 estiver offline ou lento, o LiteLLM cai automaticamente para OpenRouter:
- llama3.1-8b → gpt-4o
- qwen2.5-coder → deepseek-r1
- hermes-local → claude-sonnet

## VPN UFSC → Ollama remoto

O container `litellm` compartilha a rede de um sidecar (`ufsc-vpn`, em
[`vpn/`](vpn/)) que mantém um túnel IKEv2 sempre ativo até `vpn.ufsc.br` —
assim o modelo `ufsc-ollama` no `config.yaml` consegue alcançar
`ollama.vlab.ufsc.br`.

### Credenciais

- `UFSC_VPN_USERNAME` no `.env`: **idUFSC completo**, formato
  `nome.sobrenome@ufsc.br` — nunca a variante `@grad` ou `@posgrad` (a UFSC
  rejeita). `UFSC_VPN_PASSWORD`: a senha normal da tua conta UFSC.
  ⚠️ Se essa senha tiver caractere `"` (aspas duplas), o `ipsec.secrets`
  quebra (`${UFSC_PASSWORD}` é substituído dentro de `"..."` no template) —
  nesse caso específico só dá pra contornar trocando a senha da conta UFSC.
- `UFSC_OLLAMA_API_BASE`: **sem** usuário/senha na URL — só
  `https://ollama.vlab.ufsc.br/v1`. O Basic Auth vai no
  `UFSC_OLLAMA_AUTH_HEADER` (`Basic <base64 de user:senha>`), não embutido
  na URL — se a senha tiver caractere especial (`:` `@` `/` `?` `#` `%`),
  embutir na URL quebra o parsing de `user:senha@host`; base64 não tem esse
  problema.

### Coisas que só se confirma rodando de verdade

1. **Split-tunnel**: depois de subir, `docker exec sb_ufsc_vpn ip route` —
   espera-se só rotas específicas da rede da UFSC, não um `0.0.0.0/0`
   substituindo a rota padrão. Se a UFSC empurrar full-tunnel, o LiteLLM
   perde acesso a Postgres/Redis (`192.168.0.210`), Apollo (`192.168.0.217`)
   e OpenRouter — nesse caso a arquitetura de sidecar único não serve, tem
   que revisar (ex.: um proxy dedicado só pra essa chamada específica).
2. **Basic Auth do Ollama**: já configurado via `extra_headers` (header
   `Authorization`), não na URL — a senha da UFSC tem caractere especial
   que quebraria o `user:senha@host`. Gerar o valor de
   `UFSC_OLLAMA_AUTH_HEADER` com `echo -n 'usuario:senha' | base64` e
   prefixar com `Basic ` no `.env`. Se ainda assim der 401, confirmar que o
   `echo -n` não deixou passar quebra de linha (`-n` é obrigatório).
3. **Validação de certificado do servidor** (`rightauth=pubkey` no
   `ipsec.conf`): se o `ipsec statusall` mostrar erro de validação de
   certificado, buscar o certificado da CA da UFSC/ICPEdu e montar em
   `/etc/ipsec.d/cacerts/` dentro do container — **não** desabilitar a
   validação pra "resolver".

### Deploy / debug

```bash
docker compose up -d ufsc-vpn
docker logs sb_ufsc_vpn                    # confirmar "generating CHILD_SA" / ESTABLISHED
docker exec sb_ufsc_vpn ipsec statusall    # status detalhado do túnel
docker exec sb_ufsc_vpn ip route           # confirmar split-tunnel

docker compose up -d litellm               # recria com o network_mode novo
curl http://192.168.0.211:4000/health      # confirmar que nada quebrou
```