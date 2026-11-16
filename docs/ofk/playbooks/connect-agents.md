---
type: Playbook
title: Connect Agents to the Xereta/Hermes/Hindsight MCP Stack
description: OpenCode and Claude Code MCP configurations to reach the knowledge stack (Xereta gateway + Hermes MCP + Hindsight) from the notebook via Tailscale.
tags: [agents, mcp, xereta, hermes, hindsight, tailscale]
status: stable
generated: { by: human:schiva, at: 2026-11-16T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-16T00:00:00-03:00 }
stale_after: 2027-11-16T00:00:00-03:00
sources:
  - id: xereta-agents
    resource: https://github.com/SchiavonJP/xereta/blob/main/docs/AGENTS.md
    title: Xereta agent context — MCP surface, migration checklist
  - id: hermes-mcp
    resource: https://github.com/SchiavonJP/homelabzin/blob/main/LXC_2_hermes_mcp/server.py
    title: Hermes MCP server (CT107, :3100/mcp)
---

# Connect Agents to the MCP/Knowledge Stack

> **Goal**: Give agents on the notebook (and anywhere on the Tailscale tailnet) read access to:
> 1. **Xereta gateway** (`:3101/mcp`) — full app actions + vault/skills/memory reads (bearer auth)
> 2. **Hermes MCP** (`:3100/mcp`) — raw vault/skills/memory tools (unauthenticated on LAN)
> 3. **Hindsight API** (`:8888`) — bank queries, consolidation triggers (HTTP, optional)

The Mini PC (`192.168.0.12`) is the **Tailscale subnet router** advertising `192.168.0.0/24`. Agents on the notebook install Tailscale and reach LAN IPs directly.

---

## Network topology (2026-11-16)

| Service | Host | Port | Auth | Notes |
|---------|------|------|------|-------|
| Xereta MCP gateway | CT234 (post-cutover) / CT107 (interim) | 3101 | `Authorization: Bearer <XERETA_AGENT_READ_TOKEN>` | `https://xereta.joaopaulo.me/mcp` (Cloudflare Tunnel) or `http://192.168.0.234:3101/mcp` (tailnet) |
| Hermes MCP | CT107 | 3100 | None (LAN) | `http://192.168.0.213:3100/mcp` |
| Hindsight API | CT234 | 8888 | None (LAN) | `http://192.168.0.234:8888` (also CT107 `:8888` loopback) |
| Hindsight MCP | CT234 | 9999 | None (LAN) | `http://192.168.0.234:9999/mcp` |

**Pre-cutover** (today): replace `192.168.0.234` with `192.168.0.213` for Xereta; Hermes and Hindsight unchanged.

---

## 1. Xereta Agent Read Token

Token lives in the private runtime env on each host:

```bash
# CT107 (current) or CT234 (post-cutover)
cat /root/xereta/.env | grep XERETA_AGENT_READ_TOKEN
# XERETA_AGENT_READ_TOKEN=<secret>
```

**Never commit this token.** Agents receive it via their config/env.

---

## 2. OpenCode Configuration (`~/.config/opencode/opencode.json`)

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "xereta": {
      "type": "http",
      "url": "https://xereta.joaopaulo.me/mcp",
      "headers": {
        "Authorization": "Bearer ${XERETA_AGENT_READ_TOKEN}"
      }
    },
    "hermes": {
      "type": "http",
      "url": "http://192.168.0.213:3100/mcp"
    },
    "hindsight": {
      "type": "http",
      "url": "http://192.168.0.234:8888"
    }
  }
}
```

- `${XERETA_AGENT_READ_TOKEN}` is expanded from the environment (set in your shell profile or `opencode.json` env block).
- Use `http://192.168.0.213:3101/mcp` for Xereta **before** the tunnel swap; Cloudflare hostname works for both.
- On the tailnet, LAN IPs are reachable directly; the public hostname also resolves.

### Verify

```bash
export XERETA_AGENT_READ_TOKEN="<value from /root/xereta/.env>"
opencode mcp list
# Should show: xereta (connected), hermes (connected), hindsight (connected)
opencode mcp call xereta xereta_status
```

---

## 3. Claude Code Configuration (`~/.claude/mcp.json`)

```json
{
  "mcpServers": {
    "xereta": {
      "command": "npx",
      "args": ["@modelcontextprotocol/inspector", "https://xereta.joaopaulo.me/mcp"],
      "env": {
        "MCP_AUTH_HEADER": "Authorization: Bearer ${XERETA_AGENT_READ_TOKEN}"
      }
    },
    "hermes": {
      "command": "npx",
      "args": ["@modelcontextprotocol/inspector", "http://192.168.0.213:3100/mcp"]
    },
    "hindsight": {
      "command": "npx",
      "args": ["@modelcontextprotocol/inspector", "http://192.168.0.234:8888"]
    }
  }
}
```

Claude Code uses the MCP Inspector as an HTTP→stdio bridge. The `MCP_AUTH_HEADER` env var is injected by the inspector.

> **Note**: For Claude Desktop, the config is `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows) — same structure.

---

## 4. Available Tool Surfaces

### Xereta (`xereta`)

| Group | Tools | Backend |
|-------|-------|---------|
| Xereta actions | `xereta_status`, `xereta_request_run`, `xereta_answer_question` | App DB |
| Vault | `list_notes`, `read_note`, `search_notes`, `write_note`, `get_backlinks` | SilverBullet / AFFiNE readers |
| Skills | `list_skills`, `get_skill`, `search_skills` | `hermes-mcp` (proxied) |
| Hermes memory | `get_user_model`, `get_memory`, `search_memory`, `get_recent_synthesis` | `hermes-mcp` (proxied) |

All tools are **read-only** except `xereta_request_run` / `xereta_answer_question` (require owner session).

### Hermes (`hermes`)

Pure MCP tools (no REST):
- `list_skills`, `get_skill`, `search_skills` — central skills hub (`/skills`)
- `list_notes`, `read_note`, `search_notes`, `write_note`, `get_backlinks` — Obsidian vault (`/vault`)
- `get_user_model`, `get_memory`, `search_memory`, `get_recent_synthesis` — memory (`/opt/data`)

### Hindsight (`hindsight`)

HTTP API (not MCP yet):
- `GET /v1/default/banks` — list banks
- `POST /v1/default/banks/{bank}/memories` — ingest
- `POST /v1/default/banks/{bank}/memories/search` — semantic search
- `POST /v1/default/banks/{bank}/operations` — consolidation triggers

---

## 5. Tailscale Prerequisites

1. **Mini PC subnet router** (`192.168.0.12`):
   ```bash
   sudo tailscale up --advertise-routes=192.168.0.0/24
   # Admin console: approve the route
   ```

2. **Notebook**:
   ```bash
   tailscale up
   # verify:
   ping 192.168.0.234   # CT234
   ping 192.168.0.213   # CT107
   ```

---

## 6. Secrets Management (Never Commit)

| Secret | Source | Where used |
|--------|--------|------------|
| `XERETA_AGENT_READ_TOKEN` | `/root/xereta/.env` on CT107/CT234 | OpenCode `Authorization` header, Claude `MCP_AUTH_HEADER` |
| `LITELLM_KEY` | `/root/xereta/.env` | Indirect (via LiteLLM gateway) |
| `HINDSIGHT_TOKEN` | (if auth enabled later) | Hindsight API bearer |

**Pattern**: Store in `~/.config/opencode/env` or shell profile (`.zshrc`, `.bashrc`):
```bash
export XERETA_AGENT_READ_TOKEN="sk-..."
export LITELLM_KEY="sk-..."
```

---

## 7. Migration Notes (Post-CT234 Cutover)

| Service | Old URL (CT107) | New URL (CT234) | Action |
|---------|-----------------|-----------------|--------|
| Xereta MCP | `http://192.168.0.213:3101/mcp` | `http://192.168.0.234:3101/mcp` | Update agent configs; Cloudflare hostname `https://xereta.joaopaulo.me/mcp` unchanged |
| Hermes MCP | `http://192.168.0.213:3100/mcp` | (same — Hermes stays on CT107) | No change |
| Hindsight API | `http://192.168.0.213:8888` (loopback only) | `http://192.168.0.234:8888` | Update if accessed directly |
| Hindsight MCP | `http://192.168.0.213:9999/mcp` (loopback only) | `http://192.168.0.234:9999/mcp` | Update if used |

---

## 8. Quick Validation Checklist

```bash
# From notebook (on tailnet)
curl -H "Authorization: Bearer $XERETA_AGENT_READ_TOKEN" https://xereta.joaopaulo.me/health/ready
# → {"status":"ok"}

opencode mcp call xereta list_skills | jq '.total'
# → 42 (or whatever the current count is)

opencode mcp call hermes list_skills | jq '.total'
# → 42

curl http://192.168.0.234:8888/health
# → {"status":"healthy","database":"connected",...}
```

All three green = agents have full stack access.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `401` on Xereta MCP | Token missing/wrong | Verify `XERETA_AGENT_READ_TOKEN` matches `/root/xereta/.env` |
| `connection refused` on `192.168.0.213:*` | Not on tailnet / subnet router down | `tailscale up`; check Mini PC `tailscale status` |
| `403` on Hermes | Transport allowlist missing IP | CT107 `sb_mcp` allowlist updated 2026-11-16 for `.234`; verify `docker logs sb_mcp` |
| Hindsight `404 /banks` | Wrong path | Use `/v1/default/banks` (see Hindsight API) |