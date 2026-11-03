#!/usr/bin/env python3
"""Non-destructive knowledge-system probes. Python standard library only.

Prints JSON evidence; never changes services, retains memories, or edits notes.
The model probe sends synthetic fixtures and can incur inference usage.
"""

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


NETWORK = [
    ("proxmox-ssh", "192.168.0.200", 22),
    ("hermes-mcp", "192.168.0.213", 3100),
    ("litellm", "192.168.0.211", 4000),
    ("postgres", "192.168.0.210", 5432),
    ("affine", "192.168.0.221", 3010),
    ("minipc-ssh", "192.168.0.12", 22),
    ("notebook-ssh", "100.80.3.58", 22),
]
CONTAINERS = {
    "hermes": ["sb_hermes", "sb_mcp"],
    "router": ["sb_litellm", "sb_ufsc_vpn"],
    "affine": ["affine_server", "affine_postgres", "affine_redis"],
    "data": ["sb_postgres", "sb_redis", "sb_falkordb"],
    "minipc": ["obsidian-livesync", "nextcloud", "minipc_silverbullet"],
}
FIXTURES = {
    "en": {
        "a": "Project Cedar keeps snapshots for 14 days. Decision by the owner: backups stay local.",
        "b": "Project Cedar keeps snapshots for 30 days. This note does not explain the discrepancy.",
        "c": "An agent suggested cloud backups for Cedar. The owner has not approved that suggestion.",
    },
    "pt": {
        "a": "O projeto Cedro guarda snapshots por 14 dias. Decisão do responsável: os backups ficam locais.",
        "b": "O projeto Cedro guarda snapshots por 30 dias. Esta nota não explica a divergência.",
        "c": "Um agente sugeriu backups na nuvem para Cedro. O responsável não aprovou essa sugestão.",
    },
}
OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "retention_values_days": {"type": "array", "items": {"type": "integer"}},
        "retention_conflict": {"type": "boolean"},
        "backup_decision": {"type": "string", "enum": ["local", "cloud", "unknown"]},
        "cloud_backup_status": {"type": "string", "enum": ["approved", "suggested", "unknown"]},
        "unresolved_question": {"type": "string"},
        "evidence": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"source_id": {"type": "string"}, "quote": {"type": "string"}},
            "required": ["source_id", "quote"],
        }},
    },
    "required": ["retention_values_days", "retention_conflict", "backup_decision",
                 "cloud_backup_status", "unresolved_question", "evidence"],
}


class ProbeError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request_json(url, payload, token, timeout):
    """Do not follow redirects with credentials or emit response/error bodies."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ProbeError("invalid_endpoint")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ProbeError("response_too_large")
            # Model ids are sufficient to correlate with server logs. Never log
            # API-base headers: deployments can put credentials in endpoint URLs.
            deployment = response.headers.get("x-litellm-model-id")
            return json.loads(raw), deployment
    except urllib.error.HTTPError as exc:
        raise ProbeError("http_" + str(exc.code)) from None
    except (OSError, ValueError):
        raise ProbeError("network_or_invalid_json") from None


def run_json(argv, stdin=None, timeout=15, preserve_gate_report=False):
    try:
        result = subprocess.run(argv, input=stdin, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "blocked", "reason": "command_timeout"}
    except OSError:
        return {"status": "blocked", "reason": "command_unavailable"}
    if result.returncode and not preserve_gate_report:
        return {"status": "blocked", "reason": "command_failed", "exit_code": result.returncode}
    try:
        parsed = json.loads(result.stdout)
    except ValueError:
        if result.returncode:
            return {"status": "blocked", "reason": "command_failed", "exit_code": result.returncode}
        return {"status": "failed", "reason": "invalid_command_json"}
    if result.returncode:
        evidence = parsed.get("evidence") if isinstance(parsed, dict) else None
        if not (isinstance(evidence, dict) and isinstance(evidence.get("gate"), str)
                and evidence.get("status") in {"failed", "blocked"}):
            return {"status": "blocked", "reason": "command_failed", "exit_code": result.returncode}
        parsed["process_exit_code"] = result.returncode
    return parsed


def network_probe(timeout):
    def check(endpoint):
        name, host, port = endpoint
        started = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                status = "passed"
        except OSError:
            status = "blocked"
        return {"service": name, "host": host, "port": port, "status": status,
                "seconds": round(time.monotonic() - started, 3)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(NETWORK)) as pool:
        checks = list(pool.map(check, NETWORK))
    return {"gate": "G0", "status": "partial" if any(x["status"] == "passed" for x in checks) else "blocked",
            "checks": checks, "remaining": "Authenticated version, mount, capacity and backup inventory."}


def container_inventory(name):
    # Explicit field selection prevents Docker's environment/labels from leaking secrets.
    template = ('{"name":{{json .Name}},"configured_image":{{json .Config.Image}},'
                '"image_id":{{json .Image}},"state":{{json .State.Status}},'
                '"mounts":{{json .Mounts}}}')
    result = run_json(["docker", "inspect", "--format", template, name])
    if "image_id" in result:
        result["repo_digests"] = run_json(["docker", "image", "inspect", "--format",
                                           "{{json .RepoDigests}}", result["image_id"]])
    return result


def vault_inventory(path):
    mount = run_json(["findmnt", "--json", "--target", path])
    filesystems = mount.get("filesystems", [])
    if not filesystems or filesystems[0].get("fstype") != "fuse.sshfs":
        return {"status": "blocked", "reason": "verified_sshfs_mount_required", "mount": mount}
    # Do not traverse a potentially unavailable FUSE mount in this process.
    # The subprocess deadline bounds file reads and directory traversal.
    code = """
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1]); files=sorted(x for x in p.rglob('*.md') if '.obsidian' not in x.parts)
samples=[]
for f in files[:3]:
 samples.append({'path':str(f.relative_to(p)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'mtime':f.stat().st_mtime})
print(json.dumps({'markdown_count':len(files),'sample_files':samples}))
"""
    scan = run_json([sys.executable, "-c", code, path], timeout=20)
    return {"status": "partial" if "markdown_count" in scan else "blocked",
            "mount": mount, "scan": scan,
            "remaining": "Compare sample hashes with the active notebook; prove snapshot and mirror freshness."}


def inventory_probe(role, vault_path):
    disk = shutil.disk_usage(".")
    result = {"gate": "G0/G1", "status": "partial", "role": role,
              "host": socket.gethostname(), "filesystem_free_bytes": disk.free,
              "containers": {name: container_inventory(name) for name in CONTAINERS[role]}}
    if Path("/proc/meminfo").exists():
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                result["memory_available_kib"] = int(line.split()[1])
    if all("reason" in item for item in result["containers"].values()):
        result["status"] = "blocked"
    if role == "hermes":
        result["vault"] = vault_inventory(vault_path)
        code = """
import json,os
from pathlib import Path
roots={Path('/opt/data'),Path(os.environ.get('HERMES_HOME',str(Path.home()/'.hermes')))}
found=[]
for root in roots:
 for relative in ['USER.md','MEMORY.md','memories/USER.md','memories/MEMORY.md','config.yaml','hindsight/config.json']:
  p=root/relative
  if p.is_file(): found.append({'path':str(p),'bytes':p.stat().st_size})
print(json.dumps({'files':found,'contents_read':False}))
"""
        result["hermes_files"] = run_json(["docker", "exec", "sb_hermes", "python3", "-c", code])
    result["remaining"] = "Verify runtime versions, backup restore, correct source identity, and workload capacity."
    return result


def validate_fixture(output, sources):
    if not isinstance(output, dict):
        return {"object": False}
    evidence = output.get("evidence")
    valid_evidence = isinstance(evidence, list) and bool(evidence)
    source_ids = set()
    if valid_evidence:
        for entry in evidence:
            if not isinstance(entry, dict):
                valid_evidence = False
                break
            source_id, quote = entry.get("source_id"), entry.get("quote")
            if not isinstance(source_id, str) or source_id not in sources or not isinstance(quote, str) or not quote.strip() or quote not in sources[source_id]:
                valid_evidence = False
                break
            if set(entry) != {"source_id", "quote"}:
                valid_evidence = False
            source_ids.add(source_id)
    days = output.get("retention_values_days")
    return {
        "schema_fields": set(output) == set(OUTPUT_SCHEMA["required"]),
        "both_retention_values": isinstance(days, list) and len(days) == 2 and all(type(x) is int for x in days) and sorted(days) == [14, 30],
        "contradiction_detected": output.get("retention_conflict") is True,
        "explicit_decision_preserved": output.get("backup_decision") == "local",
        "suggestion_not_approved": output.get("cloud_backup_status") == "suggested",
        "question_present": isinstance(output.get("unresolved_question"), str) and bool(output["unresolved_question"].strip()),
        "quotes_grounded": valid_evidence,
        "all_sources_cited": source_ids == set(sources),
    }


def deployment_probe(models, timeout):
    """Return selected routing fields, never the full model-info response."""
    key = os.environ.get("LITELLM_MASTER_KEY")
    if not key:
        return {"gate": "G0/G3/deployments", "status": "blocked", "reason": "LITELLM_MASTER_KEY_missing"}
    base = os.environ.get("KNOWLEDGE_LITELLM_BASE_URL", "http://127.0.0.1:4000/v1").rstrip("/")
    endpoint = base.removesuffix("/v1") + "/model/info"
    try:
        response, _ = request_json(endpoint, None, key, timeout)
        if not isinstance(response, dict) or not isinstance(response.get("data"), list):
            raise ProbeError("invalid_model_info")
        deployments = []
        for item in response["data"]:
            if not isinstance(item, dict) or item.get("model_name") not in models:
                continue
            params, info = item.get("litellm_params", {}), item.get("model_info", {})
            if not isinstance(params, dict) or not isinstance(info, dict):
                continue
            api_base = params.get("api_base")
            if isinstance(api_base, str) and api_base.startswith("os.environ/"):
                api_base = os.environ.get(api_base.removeprefix("os.environ/"))
            host = urllib.parse.urlsplit(api_base).hostname if isinstance(api_base, str) else None
            deployments.append({"alias": item["model_name"], "deployment_id": info.get("id"),
                                "provider_model": params.get("model"), "backend_host": host,
                                "order": params.get("order"), "timeout": params.get("timeout")})
        return {"gate": "G0/G3/deployments", "status": "partial" if deployments else "blocked",
                "deployments": deployments,
                "remaining": "Match the smoke test's deployment_id to this inventory; a final deployment does not establish the full fallback history."}
    except (ProbeError, ValueError) as exc:
        return {"gate": "G0/G3/deployments", "status": "blocked",
                "reason": str(exc) if isinstance(exc, ProbeError) else "invalid_backend_url"}


def model_probe(models, timeout, languages=None):
    key = os.environ.get("LITELLM_MASTER_KEY")
    if not key:
        return {"gate": "G3/model-smoke", "status": "blocked", "reason": "LITELLM_MASTER_KEY_missing"}
    base = os.environ.get("KNOWLEDGE_LITELLM_BASE_URL", "http://127.0.0.1:4000/v1").rstrip("/")
    tests = []
    for model in models:
        for language in languages if languages is not None else FIXTURES:
            sources = FIXTURES[language]
            payload = {
                "model": model, "temperature": 0, "max_tokens": 1200,
                "messages": [
                    {"role": "system", "content": "Extract only from the supplied synthetic source notes. Do not reconcile conflicting retention values without evidence. Distinguish an explicit owner decision from an unapproved agent suggestion. Ask one question about the unresolved retention policy, in the source language. Cite each source with an exact, nonempty quote."},
                    {"role": "user", "content": json.dumps(sources, ensure_ascii=False)},
                ],
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "knowledge_gate", "strict": True, "schema": OUTPUT_SCHEMA}},
            }
            started = time.monotonic()
            test = {"requested_model": model, "language": language,
                    "fixture_sha256": hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()}
            try:
                response, deployment = request_json(base + "/chat/completions", payload, key, timeout)
                if not isinstance(response, dict):
                    raise ProbeError("invalid_completion")
                choices = response.get("choices") or []
                if not choices or not isinstance(choices[0], dict):
                    raise ProbeError("missing_completion")
                choice = choices[0]
                content = choice.get("message", {}).get("content")
                if not isinstance(content, str):
                    raise ProbeError("missing_content")
                try:
                    parsed = json.loads(content)
                except ValueError:
                    raise ProbeError("invalid_structured_output") from None
                assertions = validate_fixture(parsed, sources)
                test.update({"status": "passed" if all(assertions.values()) and choice.get("finish_reason") == "stop" else "failed",
                             "assertions": assertions, "finish_reason": choice.get("finish_reason"),
                             # These outputs derive exclusively from synthetic fixtures.
                             # Preserve the observed value instead of guessing why an assertion failed.
                             "observed_output": parsed,
                             "returned_model": response.get("model"), "deployment_id": deployment,
                             "backend_attribution": "correlate deployment id with router logs" if deployment else "unverified",
                             "usage": response.get("usage")})
            except ProbeError as exc:
                test.update({"status": "failed", "reason": str(exc)})
            test["seconds"] = round(time.monotonic() - started, 3)
            tests.append(test)
    return {"gate": "G3/model-smoke", "fixture_version": 1,
            "status": "partial" if all(t["status"] == "passed" for t in tests) else "failed",
            "model_smoke_passed": all(t["status"] == "passed" for t in tests), "tests": tests,
            "remaining": "Confirm actual backend/fallback; test Hindsight retain, consolidation, reflect, deletion, graph, persistence and resource use."}


def affine_probe(base, workspace, doc_id, timeout):
    token = os.environ.get("AFFINE_MCP_TOKEN")
    if not token or not workspace:
        return {"gate": "G2", "status": "blocked", "reason": "AFFINE_MCP_TOKEN_and_workspace_id_required",
                "remaining": "Inventory the installed release and enable a scoped MCP credential through the normal settings UI."}
    url = base.rstrip("/") + "/api/workspaces/" + urllib.parse.quote(workspace, safe="") + "/mcp"

    def rpc(method, params, call_id):
        response, _ = request_json(url, {"jsonrpc": "2.0", "id": call_id, "method": method, "params": params}, token, timeout)
        if not isinstance(response, dict) or "error" in response or not isinstance(response.get("result"), dict):
            raise ProbeError("mcp_rpc_error")
        return response["result"]

    try:
        initialized = rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                          "clientInfo": {"name": "knowledge-gates", "version": "1"}}, 1)
        listed = rpc("tools/list", {}, 2)
        tools = {item["name"] for item in listed.get("tools", []) if isinstance(item, dict) and isinstance(item.get("name"), str)}
        result = {"gate": "G2", "status": "partial", "server_info": initialized.get("serverInfo"),
                  "tools": sorted(tools), "read_tools_advertised": {"read_document", "doc_search"} <= tools,
                  "write_tools_advertised": {"create_document", "update_document"} <= tools,
                  "write_test_performed": False,
                  "remaining": "Verify complete enumeration/change tracking, then creation, update, human response and edit conflicts in disposable pages."}
        if doc_id:
            document = rpc("tools/call", {"name": "read_document", "arguments": {"docId": doc_id}}, 3)
            text = "\n".join(part.get("text", "") for part in document.get("content", []) if part.get("type") == "text")
            # Readability is evidence only. Never include the original document in the report.
            result["document_read"] = {"status": "failed" if document.get("isError") or not text.strip() else "passed",
                                       "sha256": hashlib.sha256(text.encode()).hexdigest(), "characters": len(text)}
        return result
    except ProbeError as exc:
        return {"gate": "G2", "status": "blocked", "reason": str(exc)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    network = sub.add_parser("network", help="TCP reachability only; no authentication")
    network.add_argument("--timeout", type=float, default=4)
    inventory = sub.add_parser("inventory", help="Run on the relevant Docker host")
    inventory.add_argument("--role", required=True, choices=CONTAINERS)
    inventory.add_argument("--vault-path", default="/mnt/obsidian-vault")
    model = sub.add_parser("model", help="Synthetic structured-output tests through LiteLLM")
    model.add_argument("--models", nargs="+", default=["ufsc-vision"])
    model.add_argument("--languages", nargs="+", choices=FIXTURES, default=list(FIXTURES))
    model.add_argument("--timeout", type=float, default=120)
    model.add_argument("--container", default="sb_litellm")
    model.add_argument("--inside-container", action="store_true", help=argparse.SUPPRESS)
    deployments = sub.add_parser("deployments", help="Read selected gateway routing fields; no inference")
    deployments.add_argument("--models", nargs="+", default=["ufsc-vision"])
    deployments.add_argument("--timeout", type=float, default=15)
    deployments.add_argument("--container", default="sb_litellm")
    deployments.add_argument("--inside-container", action="store_true", help=argparse.SUPPRESS)
    affine = sub.add_parser("affine", help="Read-only MCP capability and optional document probe")
    affine.add_argument("--base-url", default="http://127.0.0.1:3010")
    affine.add_argument("--workspace-id", default=os.environ.get("AFFINE_WORKSPACE_ID"))
    affine.add_argument("--doc-id")
    affine.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args(argv)
    if hasattr(args, "timeout") and args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.command == "network":
        evidence = network_probe(args.timeout)
    elif args.command == "inventory":
        evidence = inventory_probe(args.role, args.vault_path)
    elif args.command == "affine":
        evidence = affine_probe(args.base_url, args.workspace_id, args.doc_id, args.timeout)
    elif args.inside_container:
        evidence = (deployment_probe(args.models, args.timeout) if args.command == "deployments"
                    else model_probe(args.models, args.timeout, args.languages))
    else:
        source = Path(__file__).read_text()
        child_args = ["docker", "exec", "-i", args.container, "python3", "-", args.command,
                      "--inside-container", "--timeout", str(args.timeout), "--models", *args.models]
        if args.command == "model":
            child_args.extend(["--languages", *args.languages])
        request_count = len(args.models) * len(args.languages) if args.command == "model" else 1
        evidence = run_json(child_args, stdin=source, timeout=args.timeout * request_count + 20,
                            preserve_gate_report=True)
        print(json.dumps(evidence, indent=2, ensure_ascii=False))
        outcome = evidence.get("evidence", evidence)
        if args.command == "model":
            return 0 if outcome.get("model_smoke_passed") else 1
        return 1 if outcome.get("status") in {"failed", "blocked"} else 0
    report = {"recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "probe_version": 3, "evidence": evidence}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if evidence.get("status") in {"failed", "blocked"} else 0


if __name__ == "__main__":
    sys.exit(main())
