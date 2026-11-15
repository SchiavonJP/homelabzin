# homelabzin

Configuration-as-code and knowledge base for a Proxmox homelab: LXC containers, Mini PC services, personal machines, and operational tooling.

## Start here

| Document | Purpose |
|----------|---------|
| **[docs/ofk/index.md](docs/ofk/index.md)** | OKF v0.2 knowledge bundle — the structured, agent-readable source of truth (infrastructure, LXC containers, services, playbooks) |
| [CLAUDE.md](CLAUDE.md) | Agent context — inventory, rules, actor conventions |
| [HOMELAB.md](HOMELAB.md) | Narrative overview (historical; OKF bundle is authoritative for current state) |
| [plan.md](plan.md) | Implementation plan and decisions log |

## Layout

```
docs/ofk/          OKF knowledge bundle (concepts with frontmatter, indexes, logs)
LXC_<n>_<name>/    Per-container configs: docker-compose.yml, readme, .env.example
                   ⚠ folder numbers ≠ Proxmox VMIDs — see docs/ofk/infrastructure/proxmox-host.md
minipc/            CasaOS Mini PC services (Traefik + Cloudflare Tunnel, NFS, LiveSync…)
notebook/          Personal notebook setup (Arch, Obsidian vault, Tailscale)
migration/         Historical migration records (EndeavourOS VM)
scripts/           Operational tooling (knowledge-curator, gates, snapshot, git bundles)
apps/xereta/       Xereta application (migrating to github.com/SchiavonJP/xereta)
```

## Conventions

- Every LXC deploys via sparse checkout of its folder + `docker compose up -d` (see [Bootstrap LXC](docs/ofk/playbooks/bootstrap-lxc.md)).
- Secrets stay in `.env` files on the machines — never committed.
- Documentation changes to infrastructure state should update the corresponding `docs/ofk/` concept and its `log.md`.
