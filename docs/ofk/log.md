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
