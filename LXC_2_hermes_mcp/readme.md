# LXC 2 — Hermes

Hermes Agent · motor do second brain · pipeline noturno · MCP server

## Specs recomendadas do LXC

```
CPU:  2 cores
RAM:  4 GB
Disk: 20 GB
```

## Pré-requisitos

```bash
# LXC Debian 12 com nesting=1
# features: keyctl=1,nesting=1  no /etc/pve/lxc/<id>.conf

apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
```

## Setup — ordem importante

O Hermes precisa de um wizard de setup interactivo antes de subir em modo daemon.

### Passo 1 — Setup inicial (só uma vez)

```bash
# Cria o directório de dados
mkdir -p ~/.hermes

# Corre o wizard interactivo
docker run -it --rm \
  -v ~/.hermes:/opt/data \
  nousresearch/hermes-agent:latest setup
```

O wizard vai perguntar:
- LLM provider → escolhe **OpenAI-compatible**
- API base URL → `http://<IP_LXC4>:4000`
- API key → valor do LITELLM_MASTER_KEY
- Modelo default → `auto-heavy`
- Gateway (Telegram, Discord) → configura agora ou depois

### Passo 2 — Deploy via Git

```bash
# SSH access (run once from Proxmox host)
pct exec <VMID> -- mkdir -p /root/.ssh
cat ~/.ssh/id_ed25519.pub | pct exec <VMID> -- tee /root/.ssh/authorized_keys
pct exec <VMID> -- chmod 700 /root/.ssh
pct exec <VMID> -- chmod 600 /root/.ssh/authorized_keys

# Clone only this folder (run on LXC 2)
git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/second-brain-automation.git
cd second-brain-automation
git sparse-checkout init --cone
git sparse-checkout set LXC_2_hermes_mcp
git checkout main
cd LXC_2_hermes_mcp
```

### Passo 3 — Editar variáveis

```bash
cp .env.example .env
nano .env   # fill in LITELLM_MASTER_KEY, HERMES_DASHBOARD_PASSWORD, POSTGRES_PASSWORD
```

### Passo 4 — Subir

```bash
docker compose up -d
docker compose ps
```

### Pull updates

```bash
cd ~/second-brain-automation && git pull
cd LXC_2_hermes_mcp && docker compose up -d
```

## Vault Obsidian

O vault é sincronizado via CouchDB (Obsidian LiveSync) em `https://obsidian.joaopaulo.me`.
Integração directa com o MCP server está pendente — os endpoints de vault retornam vazio por agora.

## Skills centralizadas

```bash
# Clonar o teu repo de skills
git clone https://github.com/<teu-user>/agent-skills /opt/second-brain/hermes/skills

# Manter actualizado (cron diário)
echo "0 6 * * * git -C /opt/second-brain/hermes/skills pull" >> /etc/crontab
```

## Dashboard

```
http://<IP_LXC2>:9119
login: admin / <HERMES_DASHBOARD_PASSWORD>
```

## Verificar pipeline

```bash
# Ver logs do Hermes em tempo real
docker logs -f sb_hermes

# Ver skills aprendidas
docker exec sb_hermes hermes skills list

# Ver memória actual
docker exec sb_hermes hermes memory show

# Testar MCP server
curl http://localhost:3100/health
curl http://localhost:3100/skills
```

## Pipeline noturno

O Hermes suporta cron scheduling nativo. Configura via dashboard ou CLI:

```bash
# Exemplo — síntese noturna às 02:00
docker exec sb_hermes hermes schedule add \
  --cron "0 2 * * *" \
  --task "Analisa as notas adicionadas hoje ao vault, identifica gaps de conhecimento e gera 3 study provocations. Salva em /vault/provocations/$(date +%Y-%m-%d).md"
```

## Acesso via Telegram (opcional)

```bash
# 1. Cria um bot em @BotFather no Telegram
# 2. Adiciona o token no .env: TELEGRAM_BOT_TOKEN=
# 3. Configura o gateway
docker exec -it sb_hermes hermes gateway setup
```

Depois do setup, consegues interagir com o Hermes directamente no Telegram,
mesmo fora de casa, sem expor o dashboard publicamente.

## Monitoramento (Dockhand/Hawser)

Agente Hawser (`sb_hawser`, porta 2376) registrado no Dockhand (LXC 7) —
detecta atualização de imagem disponível (badge, não aplica sozinho). Ver
`HAWSER_TOKEN` no `.env.example`.