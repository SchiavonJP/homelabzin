# LXC Containers

Containers running on the [Proxmox host](../infrastructure/proxmox-host.md). The folder number in the repo (`LXC_<n>_*`) does **not** match the Proxmox VMID — see each concept's Identity table or the host inventory.

## Always-on tier

* [LXC 2 — Hermes MCP](lxc-2-hermes-mcp.md) - AI agent + MCP server + Xereta host (CT107, .213)
* [LXC 4 — LiteLLM](lxc-4-litellm.md) - LLM router + Langfuse (CT105, .211)
* [LXC 5 — Dados](lxc-5-dados.md) - Postgres, Redis, FalkorDB (CT104, .210)
* [LXC 7 — Monitor Stack](lxc-7-docker-stack.md) - Kuma, Dockhand, Homepage (CT109, .216)
* [LXC 8 — Apollo](lxc-8-llama.md) - CPU embeddings (CT110, .217)
* [LXC 12 — Personal Hub](lxc-12-personal-hub.md) - AFFiNE, Hawser, Ryot (CT106, .221)
* [LXC 13 — Camera](lxc-13-camera.md) - motionEye dog cam (CT114, .222)

## On-demand tier (stopped when unused)

* [LXC 9 — Jellyfin](lxc-9-jellyfin.md) - Media streaming (CT111, .218)
* [LXC 10 — Arr Stack](lxc-10-arr.md) - Media/music automation (CT112, .219)
* [LXC 11 — Downloads](lxc-11-downloads.md) - qBittorrent (CT113, .220)

## Retired

* LXC 1 (Traefik) — replaced by [Traefik on Mini PC](../services/traefik-minipc.md)
* LXC 3 (Odysseus) — container CT108 kept stopped for rollback
