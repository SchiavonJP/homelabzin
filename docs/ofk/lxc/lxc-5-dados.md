---
type: LXC Container
title: LXC 5 — Dados
description: Dedicated data layer — Postgres 17, Redis 7, FalkorDB. VMID 104, IP 192.168.0.210, LAN only.
resource: LXC_5_dados/readme.md
tags: [lxc, database, postgres, redis, falkordb]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: lxc-readme
    resource: ../../LXC_5_dados/readme.md
    title: LXC 5 readme — setup and connection strings
    author: human:schiva
---

# Identity

| Item | Value |
|------|-------|
| VMID | 104 (hostname `sb-dados`) |
| IP | 192.168.0.210 (LAN only) |
| Resources | 2 cores · 2 GB RAM · 512 MB swap · 20 GB disk |
| Ports | 5432 (Postgres) · 6379 (Redis) · 6380 + 3000 (FalkorDB, localhost-bound) |

# Services

| Container | Port | Role |
|-----------|------|------|
| `sb_postgres` | 5432 | Postgres 17 — databases: `hermes`, `odysseus`, `secondbrain`, `dockhand`, `knowledge_curator` ([Xereta](../services/xereta.md)) |
| `sb_redis` | 6379 | Redis 7, AOF persistence — LiteLLM response cache |
| `sb_falkordb` | 6380 / 3000 | FalkorDB (Cypher-compatible) — reserved for knowledge-graph use |

Design principle: data layer decoupled from services so any LXC can restart independently.[^lxc-readme]

# Connection reference

```
postgresql://secondbrain:<senha>@192.168.0.210:5432/<database>
redis://:<senha>@192.168.0.210:6379
redis://:<senha>@192.168.0.210:6380     # FalkorDB graph
```

* Postgres and Redis: reachable on the LAN ports above.
* FalkorDB browser (3000) and graph port bind to 127.0.0.1 of the LXC — use SSH tunnel `ssh -L 3000:localhost:3000 root@192.168.0.210` for the browser UI.
* Create-database pattern: `docker exec -it sb_postgres psql -U secondbrain -c "CREATE DATABASE <name>;"`

# Consumers

* [LXC 2 — Hermes](lxc-2-hermes-mcp.md) → `hermes` db
* [LXC 4 — LiteLLM](lxc-4-litellm.md) → Redis cache, `litellm` db
* [LXC 7 — Monitor](lxc-7-docker-stack.md) → `dockhand` db
* [Xereta](../services/xereta.md) → `knowledge_curator` db, role `xereta`

[^lxc-readme]: LXC_5_dados/readme.md.
