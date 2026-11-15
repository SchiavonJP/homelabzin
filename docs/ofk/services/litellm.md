---
type: Service
title: LiteLLM Router
description: Single OpenAI-compatible LLM endpoint with 9 approved aliases, Langfuse tracing, and UFSC VPN backends. Runs on CT105.
resource: LXC_4_litellm/readme.md
tags: [ai, litellm, router, openrouter, langfuse]
status: stable
generated: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
verified: { by: human:schiva, at: 2026-11-14T00:00:00-03:00 }
stale_after: 2027-11-14T00:00:00-03:00
sources:
  - id: lxc-readme
    resource: ../../LXC_4_litellm/readme.md
    title: LXC 4 readme — catalog review 2026-11-09
    author: human:schiva
    last_modified: 2026-11-09T00:00:00-03:00
---

# Overview

Central OpenAI-compatible router (`http://192.168.0.211:4000/v1`). No consumer knows which backend serves a request; routing, fallbacks between groups, and Redis response caching are handled here. Traces and costs land in Langfuse (`langfuse.joaopaulo.me`). Container runs on [LXC 4](../lxc/lxc-4-litellm.md) — see that concept for the full approved catalog and operational lessons.

# Consumed by

* [Hermes](../lxc/lxc-2-hermes-mcp.md) — `generalist` + selectable aliases (`custom:litellm` provider)
* [Xereta](xereta.md) — `generalist` for review prompts, `embed` for embeddings
* Any MCP-connected agent via Hermes

# Invariants

* `embed` (bge-m3 on [Apollo](../lxc/lxc-8-llama.md)) is the only embeddings route — no fallback exists; vector space must not change.
* Alias list is curated (2026-11-09 review): additions require the same audit process (`config.proposed.yaml`, sanitized evidence in `model-audit-*.json`).[^lxc-readme]

[^lxc-readme]: LXC_4_litellm/readme.md.
