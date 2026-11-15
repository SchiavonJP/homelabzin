---
type: LXC Container
title: LXC 4 — LiteLLM
description: LLM router with Langfuse observability and UFSC VPN — single OpenAI-compatible endpoint for the whole stack. VMID 105.
resource: LXC_4_litellm/readme.md
tags: [lxc, ai, litellm, langfuse, vpn]
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

# Identity

| Item | Value |
|------|-------|
| VMID | 105 (hostname `sb-litellm`) |
| IP | 192.168.0.211 |
| Resources | 2 cores · 4 GB RAM · 10 GB disk |
| Access | `litellm.joaopaulo.me` (`:4000`) · `langfuse.joaopaulo.me` (`:3001`) |

> Repo folder is `LXC_4_litellm/` but the VMID is **105**.

# Services

| Container | Port | Role |
|-----------|------|------|
| `sb_litellm` | 4000 | LiteLLM proxy — OpenAI-compatible router |
| `sb_langfuse` (+ ClickHouse) | 3001 | LLM traces + costs |
| `sb_ufsc_vpn` | — | strongSwan VPN to UFSC (write⇒DNS interplay, see readme) |

# Approved model catalog (2026-11-09 review)

Nine principal options; hidden compat aliases kept (`agent`, `writer`, `extraction` → `default-agent`; `auto-heavy`/`auto-light`; `ufsc-*`). Removed aliases (`oss`, `free-auto`, `ufsc-llama70b`, local chat) are not redirected.

| Alias | Backend | Role |
|---|---|---|
| `default-agent` | OpenRouter Nemotron 3.5 Super VL `:free` | General, images, tools |
| `coder` | OpenRouter Cohere North Mini Code `:free` | Code assistance |
| `fast` | OpenRouter Gemma 4 26B A4B `:free` | Small tasks |
| `reasoning` | OpenRouter Nemotron 3 Ultra `:free` | Explicit reasoning |
| `generalist` | Qwen3.8 27B, VLAB → CEOS | Text + code |
| `vision` | Qwen3.8 27B, VLAB → CEOS | Images |
| `frontier` | Qwen3.5 122B, VLAB | Large model |
| `ocr` | GLM-OCR, VLAB → CEOS | OCR |
| `embed` | bge-m3 on [Apollo](lxc-8-llama.md), CPU | Embeddings only |

`fallbacks` between registered groups (not `fallback_models` — unsupported by installed Router). No generic fallback for embeddings/OCR/UFSC routes. Catalog presence ≠ quality benchmark.[^lxc-readme]

# Operational lessons

* Avoid LiteLLM 1.82.7/1.82.8 (security incident); use `main-stable`.
* First deploy attempt auto-restored previous YAML on startup timeout — expect slow boot after host reboot (ClickHouse).
* DNS file shared by `sb_litellm`/`sb_ufsc_vpn` went empty once; restored to Docker resolver `127.0.0.11, ndots:0`. Root cause of the DNS dispute still open.
* Backups: `/root/litellm-profile-backup-20261109-175706`, `/root/litellm-dns-backup-20261109-151706` (CT 105).

# Dependencies

* [LXC 5 — Dados](lxc-5-dados.md): Redis response cache, Postgres
* [LXC 8 — Apollo](lxc-8-llama.md): `embed` alias → `192.168.0.217:8081/v1/embeddings`
* OpenRouter (free tier), VLAB/CEOS (UFSC)

[^lxc-readme]: LXC_4_litellm/readme.md, revision section 2026-11-09.
