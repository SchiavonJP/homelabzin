---
type: Service
title: Dados Data Layer
description: Postgres/Redis/FalkorDB connection reference for consumers. Runs on CT104, LAN only.
resource: LXC_5_dados/readme.md
tags: [database, postgres, redis, falkordb]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: lxc-readme
    resource: ../../LXC_5_dados/readme.md
    title: LXC 5 readme — connection strings
    author: human:schiva
---

# Overview

Shared data layer on [LXC 5](../lxc/lxc-5-dados.md) (`192.168.0.210`). Decoupled from services so each LXC restarts independently. Container/service specifics live in the LXC concept; this concept is the consumer-facing reference.

# Databases

| Database | Consumer |
|----------|----------|
| `hermes` | [Hermes](../lxc/lxc-2-hermes-mcp.md) |
| `odysseus` | legacy (CT108, stopped) |
| `secondbrain` | general / LiteLLM |
| `dockhand` | [Dockhand](dockhand.md) |
| `knowledge_curator` | [Xereta](xereta.md) (role `xereta` — pilot name kept) |

# Access patterns

* New database: `docker exec -it sb_postgres psql -U secondbrain -c "CREATE DATABASE <name>;"`
* Redis: AOF persistence; LiteLLM response cache.
* FalkorDB: localhost-bound inside the LXC (SSH tunnel for browser); reserved for future knowledge-graph work — **deferred**, no ingestion today.[^lxc-readme]

[^lxc-readme]: LXC_5_dados/readme.md.
