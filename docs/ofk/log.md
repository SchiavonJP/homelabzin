# Knowledge Base Update Log

## 2026-11-14
* **Creation**: Established OKF v0.2 knowledge bundle structure under `docs/ofk/`.
* **Creation**: Added infrastructure concepts: Proxmox host, Mini PC CasaOS, Endeavour VM, Dokploy host.
* **Creation**: Added LXC concepts for the live containers (CT104–CT114), with VMID ↔ folder-number mapping verified via `pct list`.
* **Creation**: Added service concepts: Traefik (Mini PC), LiteLLM, Dados, Xereta, Dockhand, Uptime Kuma, Homepage.
* **Creation**: Added playbooks: Bootstrap LXC, Deploy Xereta via Dokploy.
* **Note**: LXC 1 (Traefik) and LXC 3 (Odysseus) no longer exist — Traefik now runs on the Mini PC with Cloudflare Tunnel; Odysseus was retired.

## 2026-11-15
* **Update**: Verified CT234 → CT104:5432 TCP reachability (open) and `sb_postgres` external binding; recorded in [Dokploy Host](infrastructure/dokploy-host.md) and the deploy playbook.
* **Update**: [LXC 12 — Personal Hub](lxc/lxc-12-personal-hub.md) promoted `draft` → `stable` from verified `pct exec 106` data — includes `sb_xereta_affine_reader` discovery.
* **Update**: Dokploy host confirmed as the liciteria ("pncp") SaaS POC owner; concept promoted to `stable`.
* **Update**: All deploy references in per-LXC readmes repointed from `second-brain-automation` to `homelabzin` (15 files).
* **Decision**: Xereta ingress = Cloudflare Tunnel (no Dokploy SSL). Origin `192.168.0.213:3101` interim → `192.168.0.234:3101` post-cutover; port stays 3101. Cloudflare Access recommended.
* **Note**: Compose review revealed CT107 coupling — host-network Hindsight loopback, Hermes `root_hermes_data` volume, `/root/skills` bind. Migration strategy decision recorded in the deploy playbook open items.
* **Migration**: Xereta application split to its own repo (`github.com/SchiavonJP/xereta`, private, single-commit import; `apps/xereta/` removed). Strategy A decided: re-provision dependencies on CT234; MCP allowlist patch + agent-client updates recorded in the deploy playbook and the app's `docs/AGENTS.md`.

## 2026-11-16
* **Feature** (xereta repo, commit `20d151c`): pluggable `local | hermes-mcp` backends for the 6 skills/memory tools (`XERETA_SKILLS_BACKEND`, `XERETA_MEMORY_BACKEND`; default `local`). New `app/gateway.py` (settings-driven dispatch) + `app/hermes_client.py` (streamable-HTTP MCP client, per-call session, optional bearer). Error contract: `hermes_unavailable` 503 / `hermes_tool_error` 502; Hermes' graceful `{"content": null, "message": ...}` passes through. 15 new tests; suite 150 passed / 3 skipped.
* **Fix** (`LXC_2_hermes_mcp`, commits `99a9ba9`, `6c71a57`, `65f3cdf`): deployed `sb_mcp` on CT107 was still the old FastApiMCP/SSE build (tool names like `list_skills_skills_get`); rebuilt with the current FastMCP server. Three fixes were required to make streamable-HTTP work under the FastAPI mount: session-manager lifespan (`app.mount` alone never runs it), `streamable_http_path="/"` + `stateless_http` to avoid FastAPI's 307 `/mcp` → `/mcp/` redirect dance, and `TransportSecuritySettings` allowing LAN (`.213`, `.234`) + docker-internal Hosts. Old flat files backed up on CT107 (`/root/*.bak-20261116`) before overwriting.
* **Validation**: live smoke from the notebook — all 6 proxied tools (`list_skills`, `get_skill`, `search_skills`, `get_user_model`, `get_memory`, `search_memory`) return 200 against real Hermes `:3100/mcp`; `sb_hermes` healthy. Note: Hermes `get_skill`/`search_skills` return parsed `frontmatter` separately while the local backend embeds the raw frontmatter block inside `content` — accepted shape difference (hermes-mcp mode is cleaner).
* **Fix** (xereta `5e05a69`): `asyncio.run` inside sync MCP tool bodies fails because FastMCP runs them in the event loop thread — outbound Hermes calls now offload to a worker thread when a loop is running. Regression test calls `call_tool` from inside a running loop.
* **Deployed on CT107**: xereta `sb_xereta`/`sb_xereta_worker` rebuilt with the gateway code and flipped to `XERETA_SKILLS_BACKEND=hermes-mcp` + `XERETA_MEMORY_BACKEND=hermes-mcp` in `/root/xereta/.env` (backup `.env.bak-20261116`; previous image tagged `xereta:rollback-20261116`). End-to-end verified: notebook → `:3101/mcp` bearer → backends → Hermes `:3100` → live skill data; `/health/ready` ok. Rollback: retag rollback image, restore `.env` backup, `docker compose up -d`.
