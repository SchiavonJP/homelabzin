# LXC 3 — Odysseus

Interface de chat do second brain. Consome as ferramentas MCP do LXC 2 (Hermes)
e roteia modelos via LiteLLM no LXC 4.

## Specs recomendadas do LXC

```
Hostname:   sb-odysseus
Password:   (define uma senha root)
Template:   debian-12

CPU:        2 cores
RAM:        4096 MB (4 GB — Hermes acumula contexto em memória)
Swap:       1024 MB
Disk:       20 GB   (logs, memória persistente, skills, cache)

Network:    vmbr0
Name:       eth0
Bridge:     vmbr0
IPv4:       Static
IPv4/CIDR:  192.168.0.214/24  (ou o próximo IP disponível na tua rede)
Gateway:    192.168.0.1
DNS:        herdar do host
```

## Ferramentas disponíveis

### Vault Obsidian
| Ferramenta    | Descrição                                      |
|---------------|------------------------------------------------|
| list_notes    | Lista todas as notas (aceita sub-directório)   |
| read_note     | Lê conteúdo completo de uma nota              |
| search_notes  | Pesquisa por conteúdo em todas as notas       |
| write_note    | Cria ou actualiza uma nota                    |
| get_backlinks | Encontra notas que fazem link para outra      |

### Skills Hub
| Ferramenta    | Descrição                                      |
|---------------|------------------------------------------------|
| list_skills   | Lista todas as skills disponíveis              |
| get_skill     | Lê conteúdo de uma skill                      |
| search_skills | Pesquisa skills por conteúdo                  |

### Memória Hermes
| Ferramenta          | Descrição                                  |
|---------------------|--------------------------------------------|
| get_user_model      | Retorna USER.md (modelo de utilizador)     |
| get_memory          | Retorna MEMORY.md (memória de sessão)      |
| search_memory       | Pesquisa na memória acumulada              |
| get_recent_synthesis| Sínteses recentes geradas no vault         |

## Deploy via Git

```bash
# SSH access (run once from Proxmox host)
pct exec <VMID> -- mkdir -p /root/.ssh
cat ~/.ssh/id_ed25519.pub | pct exec <VMID> -- tee /root/.ssh/authorized_keys
pct exec <VMID> -- chmod 700 /root/.ssh
pct exec <VMID> -- chmod 600 /root/.ssh/authorized_keys

# Clone only this folder (run on LXC 3) — gets .env.example and mcp-servers.json
git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/homelabzin.git
cd homelabzin
git sparse-checkout init --cone
git sparse-checkout set LXC_3_Odysseus
git checkout main
```

## Setup Odysseus (deployed from its own repo)

```bash
# Clone the Odysseus application repo
git clone https://github.com/pewdiepie-archdaemon/odysseus.git /root/repo
cd /root/repo

# Configure
cp .env.example .env
# Also copy our deployment overrides:
cp ~/homelabzin/LXC_3_Odysseus/.env.example /root/repo/.env
nano /root/repo/.env   # set ODYSSEUS_ADMIN_PASSWORD

# Deploy
docker compose up -d --build
docker compose logs odysseus | grep -i "password\|admin"
```

### Pull updates (Odysseus app)

```bash
cd /root/repo
git pull
docker compose up -d --build
```

### After first login

Configure in Settings UI:
- **LLM Provider**: OpenAI-compatible, URL `http://192.168.0.211:4000/v1`, key from LXC 4 `.env`
- **MCP Server**: transport `http`, URL `http://192.168.0.213:3100/mcp`

## Notas importantes

- `SECURE_COOKIES=true` — local HTTP (`http://192.168.0.214:7000`) won't maintain sessions; always use `https://odysseus.joaopaulo.me`
- `ODYSSEUS_ADMIN_PASSWORD` only applies on **first boot with clean data** — wipe `docker volume rm root_odysseus_data` to reset

## Variáveis de ambiente

| Variável     | Default      | Descrição                          |
|--------------|--------------|------------------------------------|
| PORT         | 3100         | Porta HTTP do MCP server           |
| VAULT_PATH   | /vault       | Path do vault Obsidian (SSHFS)     |
| SKILLS_PATH  | /skills      | Path do repo de skills             |
| MEMORY_PATH  | /opt/data    | Path do volume do Hermes           |

## Testes rápidos

```bash
# Health check
curl http://localhost:3100/health

# Listar notas (via MCP JSON-RPC)
curl -X POST http://localhost:3100 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "list_notes",
      "arguments": {}
    }
  }'

# Pesquisar notas
curl -X POST http://localhost:3100 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "search_notes",
      "arguments": { "query": "segunda cérebro" }
    }
  }'

# Listar skills
curl -X POST http://localhost:3100 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "list_skills",
      "arguments": {}
    }
  }'
```

## Estrutura de directórios esperada

```
/vault/                  ← vault Obsidian (SSHFS do Mini PC)
  daily/
  projects/
  synthesis/             ← sínteses geradas pelo Hermes
  provocations/          ← study provocations geradas pelo Hermes

/skills/                 ← repo Git de skills
  engineering/
    tdd/SKILL.md
  obsidian/
    obsidian-architect/SKILL.md
  personal/

/opt/data/               ← volume do Hermes
  USER.md                ← modelo de utilizador acumulado
  MEMORY.md              ← memória de sessão
```