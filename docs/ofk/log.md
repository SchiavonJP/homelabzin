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

## 2026-11-16 (continued — Part 2 CT234 migration)

* **Hindsight replicated on CT234**: `sb_hindsight_pilot` up, healthy, connected to the shared `knowledge_pilot` DB on CT104 (pgvector). Bank `knowledge-vault-pilot` present with mission/disposition intact — zero data migration needed; DB state is the source of truth.
* **Dokploy project `xereta` created**: compose service `xereta-app` (id `EGE0G7NUONKmlc4wACEw7`) pointing at `github.com/SchiavonJP/xereta` branch `main`, compose path `compose.yml`, GitHub provider `4PenEDKpYYaWQYXlOgF16`. Environment variables pushed from CT107's `/root/xereta/.env` (includes `XERETA_SKILLS_BACKEND=hermes-mcp`, `XERETA_MEMORY_BACKEND=hermes-mcp`, `XERETA_HERMES_MCP_URL=http://192.168.0.213:3100/mcp`).
* **Compose cleanup**: `compose.yml` drops `/skills`, `/opt/data` mounts and the external `root_hermes_data` volume; `env_file` defaults to `.env` (Dokploy writes service env next to the compose file).
* **Deploy**: image built (`xereta:0.6.0`), containers `sb_xereta` (healthy) + `sb_xereta_worker` running on CT234 `network_mode: host` at `:3101`.
* **Verification**: `/health/ready` ok; MCP gateway at `192.168.0.234:3101/mcp` bearer-authenticated; all 6 proxied tools (`list_skills`, `get_skill`, `search_skills`, `get_user_model`, `get_memory`, `search_memory`) return live data from Hermes `:3100`.
* **State volume migration**: `xereta_state` (133 files: captures, gates, releases, readitlater, sync-repair) tar-copied from CT107 → CT234 `compose-program-back-end-capacitor-rjnb3y_xereta_state`; per-file checksums match.
* **Pending**: Cloudflare Tunnel origin swap (Mini PC cloudflared): service target `http://192.168.0.213:3101` → `http://192.168.0.234:3101` (same hostname `xereta.joaopaulo.me`, port 3101). Requires Mini PC access (different SSH key) — exact steps documented below.
* **Cutover**: after tunnel swap + DNS flush, stop `sb_xereta`/`sb_xereta_worker` on CT107 (rollback = `docker compose up -d` there + tunnel revert).

