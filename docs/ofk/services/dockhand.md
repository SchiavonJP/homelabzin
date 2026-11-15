---
type: Service
title: Dockhand
description: Docker container management UI with Hawser agent integration for image-update visibility. Runs on CT109.
resource: LXC_7_docker_stack/readme.md
tags: [docker, management, dockhand]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: lxc-readme
    resource: ../../LXC_7_docker_stack/readme.md
    title: LXC 7 readme — Dockhand access
    author: human:schiva
---

# Overview

Dockhand (`fnsys/dockhand`) is the Docker container management UI, running on [LXC 7 — Monitor Stack](../lxc/lxc-7-docker-stack.md) (CT109) at `dockhand.joaopaulo.me` / `192.168.0.216:3000`. State lives in the `dockhand` database on [Dados](dados.md).

# Hawser integration

Hawser agents (`sb_hawser`, port 2376) run inside monitored LXCs ([Hermes](../lxc/lxc-2-hermes-mcp.md), [Dados](../lxc/lxc-5-dados.md), others) and register in Dockhand to report available image updates as **badges** — they never apply updates by themselves. Token via `HAWSER_TOKEN` in each LXC's `.env`.[^lxc-readme]

[^lxc-readme]: LXC_7_docker_stack/readme.md and LXC readme monitor sections.
