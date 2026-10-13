#!/usr/bin/env bash
# Lista os modelos carregados (em memória) nos Ollama da UFSC e, se o modelo
# alvo não estiver carregado, carrega ele.
#
# Roda na LXC 4 (precisa do túnel VPN). Executa dentro do container litellm,
# que compartilha a rede do sidecar ufsc-vpn e já tem as variáveis UFSC_* no
# ambiente — nada de credencial passa por aqui.
#
# Uso:
#   ./ufsc-models.sh                      # ceos: lista + carrega qwen3.8:27b se faltar
#   ./ufsc-models.sh --list               # só lista, não carrega nada
#   ./ufsc-models.sh --cluster vlab       # vlab (hoje trava em POST — ver readme)
#   ./ufsc-models.sh --cluster all        # os dois
#   ./ufsc-models.sh --model llama3.3:70b --keep-alive 2h
set -euo pipefail

CONTAINER="${LITELLM_CONTAINER:-sb_litellm}"

docker exec -i "$CONTAINER" python3 - "$@" <<'PY'
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--cluster", choices=["ceos", "vlab", "all"], default="ceos")
ap.add_argument("--model", default="qwen3.8:27b")
ap.add_argument("--keep-alive", default="30m", help="quanto tempo o modelo fica em memória")
ap.add_argument("--list", action="store_true", help="só lista, não carrega")
ap.add_argument("--load-timeout", type=int, default=180)
args = ap.parse_args()

# (variável da URL base, variável do header Authorization ou None)
CLUSTERS = {
    "ceos": ("UFSC_CEOS_OLLAMA_API_BASE", None),
    "vlab": ("UFSC_OLLAMA_API_BASE", "UFSC_OLLAMA_AUTH_HEADER"),
}


def call(name, path, body=None, timeout=15):
    base_var, auth_var = CLUSTERS[name]
    # as vars apontam pro endpoint OpenAI-compat (/v1); aqui usamos a API nativa
    base = os.environ[base_var].rstrip("/").removesuffix("/v1")
    headers = {"Content-Type": "application/json"}
    if auth_var:
        headers["Authorization"] = os.environ[auth_var]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def show_loaded(name):
    models = call(name, "/api/ps").get("models", [])
    if not models:
        print("  (nenhum modelo carregado)")
    for m in models:
        gb = lambda n: f"{n / 1e9:.1f}GB"
        print(f"  {m['name']:<28} total={gb(m.get('size', 0)):<8} "
              f"vram={gb(m.get('size_vram', 0)):<8} expira={m.get('expires_at', '?')}")
    return [m["name"] for m in models]


rc = 0
for name in (["ceos", "vlab"] if args.cluster == "all" else [args.cluster]):
    print(f"== {name} ==")
    try:
        available = [m["name"] for m in call(name, "/api/tags").get("models", [])]
        print(f"  {len(available)} modelos instalados")
        loaded = show_loaded(name)
    except (urllib.error.URLError, OSError) as e:
        print(f"  ERRO ao consultar: {e}")
        rc = 1
        continue

    if args.list:
        continue
    if args.model in loaded:
        print(f"  {args.model} já está carregado.")
        continue
    if args.model not in available:
        print(f"  {args.model} NÃO está instalado neste cluster — nada pra carregar. Instalados:")
        for a in available:
            print(f"    {a}")
        rc = 1
        continue

    print(f"  carregando {args.model} (keep_alive={args.keep_alive}) ...")
    t0 = time.time()
    try:
        # prompt vazio = só carrega o modelo em memória, sem gerar nada
        call(name, "/api/generate",
             {"model": args.model, "prompt": "", "stream": False, "keep_alive": args.keep_alive},
             timeout=args.load_timeout)
    except (urllib.error.URLError, OSError) as e:
        print(f"  ERRO ao carregar após {time.time() - t0:.0f}s: {e}")
        rc = 1
        continue
    print(f"  carregado em {time.time() - t0:.0f}s. Estado atual:")
    show_loaded(name)

sys.exit(rc)
PY
