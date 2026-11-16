"""
Second Brain MCP Server
FastMCP (official MCP SDK) — vault Obsidian, skills hub e memória do Hermes
"""

import asyncio
import os
import glob
import time
from pathlib import Path
from typing import Optional

import aiofiles
import frontmatter
from contextlib import asynccontextmanager
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

# ── Configuração ──────────────────────────────────────────────────────────────

VAULT_PATH  = Path(os.environ.get("VAULT_PATH",  "/vault"))
SKILLS_PATH = Path(os.environ.get("SKILLS_PATH", "/skills"))
MEMORY_PATH = Path(os.environ.get("MEMORY_PATH", "/opt/data"))

# ── MCP server ────────────────────────────────────────────────────────────────

# streamable_http_path="/" + mount("/mcp") mirrors the xereta gateway: MCP
# lives at /mcp exactly, without FastAPI's 307 trailing-slash redirect.
mcp = FastMCP("second-brain", stateless_http=True, json_response=True, streamable_http_path="/")

# ── FastAPI app — only for /health (Docker health check) ─────────────────────

@asynccontextmanager
async def lifespan(app):
    # FastMCP's streamable transport needs its session manager task group,
    # which a plain app.mount() does not trigger.
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Second Brain MCP Server", version="2.0.0", lifespan=lifespan)
app.mount("/mcp", mcp.streamable_http_app())


# ── Helpers ───────────────────────────────────────────────────────────────────

def resolve_path(base: Path, relative: str) -> Path:
    resolved = (base / relative).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError(f"Caminho inválido: {relative}")
    return resolved


async def read_md_file(path: Path) -> dict:
    async with aiofiles.open(path, encoding="utf-8") as f:
        raw = await f.read()
    post = frontmatter.loads(raw)
    return {"frontmatter": post.metadata, "content": post.content}


async def search_in_dir(base: Path, query: str, max_results: int = 20) -> list[dict]:
    files = await asyncio.to_thread(glob.glob, str(base / "**" / "*.md"), recursive=True)
    results = []
    lower_query = query.lower()

    for file_path in files:
        if len(results) >= max_results:
            break
        try:
            data = await read_md_file(Path(file_path))
            searchable = (data["content"] + str(data["frontmatter"])).lower()
            if lower_query in searchable:
                idx = searchable.find(lower_query)
                start = max(0, idx - 100)
                snippet = data["content"][start:start + 300].strip()
                results.append({
                    "file": str(Path(file_path).relative_to(base)),
                    "snippet": snippet,
                    "frontmatter": data["frontmatter"],
                })
        except Exception:
            continue

    return results


# ── Health (HTTP GET — used by Docker health check) ───────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "vault":  str(VAULT_PATH),
        "skills": str(SKILLS_PATH),
        "memory": str(MEMORY_PATH),
        "vault_exists":  VAULT_PATH.exists(),
        "skills_exists": SKILLS_PATH.exists(),
        "memory_exists": MEMORY_PATH.exists(),
    }


# ── VAULT tools ───────────────────────────────────────────────────────────────

@mcp.tool()
async def list_notes(subdir: str = "") -> dict:
    """Lista todas as notas Markdown no vault Obsidian."""
    base = VAULT_PATH / subdir if subdir else VAULT_PATH
    if not base.exists():
        raise ValueError(f"Directório não encontrado: {subdir}")
    files = glob.glob(str(base / "**" / "*.md"), recursive=True)
    return {"notes": [str(Path(f).relative_to(VAULT_PATH)) for f in files], "total": len(files)}


@mcp.tool()
async def read_note(note_path: str) -> dict:
    """Lê o conteúdo completo de uma nota, incluindo frontmatter e corpo."""
    path = resolve_path(VAULT_PATH, note_path)
    if not path.exists():
        raise ValueError(f"Nota não encontrada: {note_path}")
    data = await read_md_file(path)
    return {"path": note_path, **data}


@mcp.tool()
async def write_note(path: str, content: str, frontmatter_data: Optional[dict] = None) -> dict:
    """Cria ou actualiza uma nota no vault. Cria directórios intermédios automaticamente."""
    resolved = resolve_path(VAULT_PATH, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)

    if frontmatter_data:
        post = frontmatter.Post(content, **frontmatter_data)
        body = frontmatter.dumps(post)
    else:
        body = content

    async with aiofiles.open(resolved, "w", encoding="utf-8") as f:
        await f.write(body)

    return {"status": "ok", "path": path}


@mcp.tool()
async def search_notes(q: str, max_results: int = 20) -> dict:
    """Pesquisa full-text em todas as notas do vault."""
    results = await search_in_dir(VAULT_PATH, q, max_results)
    return {"query": q, "results": results, "total": len(results)}


@mcp.tool()
async def get_backlinks(note_path: str) -> dict:
    """Encontra todas as notas que referenciam a nota indicada via [[wikilink]]."""
    note_name = Path(note_path).stem
    all_files = glob.glob(str(VAULT_PATH / "**" / "*.md"), recursive=True)
    backlinks = []

    for file_path in all_files:
        rel = str(Path(file_path).relative_to(VAULT_PATH))
        if rel == note_path:
            continue
        try:
            async with aiofiles.open(file_path, encoding="utf-8") as f:
                body = await f.read()
            if f"[[{note_name}]]" in body or f"({note_path})" in body:
                backlinks.append(rel)
        except Exception:
            continue

    return {"note": note_path, "backlinks": backlinks, "total": len(backlinks)}


# ── SKILLS tools ──────────────────────────────────────────────────────────────

@mcp.tool()
async def list_skills() -> dict:
    """Lista todas as skills no hub centralizado."""
    files = glob.glob(str(SKILLS_PATH / "**" / "*.md"), recursive=True)
    skills = [str(Path(f).relative_to(SKILLS_PATH)) for f in files]
    return {"skills": skills, "total": len(skills)}


@mcp.tool()
async def get_skill(skill_path: str) -> dict:
    """Lê o conteúdo completo de uma skill."""
    path = resolve_path(SKILLS_PATH, skill_path)
    if not path.exists():
        raise ValueError(f"Skill não encontrada: {skill_path}")
    data = await read_md_file(path)
    return {"path": skill_path, **data}


@mcp.tool()
async def search_skills(q: str, max_results: int = 10) -> dict:
    """Pesquisa full-text em todas as skills disponíveis."""
    results = await search_in_dir(SKILLS_PATH, q, max_results)
    return {"query": q, "results": results, "total": len(results)}


# ── MEMORY tools ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_user_model() -> dict:
    """Retorna o USER.md — modelo de utilizador acumulado pelo Hermes."""
    path = MEMORY_PATH / "USER.md"
    if not path.exists():
        return {"content": None, "message": "USER.md ainda não existe."}
    async with aiofiles.open(path, encoding="utf-8") as f:
        content = await f.read()
    return {"content": content}


@mcp.tool()
async def get_memory() -> dict:
    """Retorna o MEMORY.md — memória de sessão acumulada pelo Hermes."""
    path = MEMORY_PATH / "MEMORY.md"
    if not path.exists():
        return {"content": None, "message": "MEMORY.md ainda não existe."}
    async with aiofiles.open(path, encoding="utf-8") as f:
        content = await f.read()
    return {"content": content}


@mcp.tool()
async def search_memory(q: str, max_results: int = 10) -> dict:
    """Pesquisa full-text na memória e ficheiros de síntese do Hermes."""
    results = await search_in_dir(MEMORY_PATH, q, max_results)
    return {"query": q, "results": results, "total": len(results)}


@mcp.tool()
async def get_recent_synthesis(days: int = 7) -> dict:
    """Retorna as sínteses mais recentes geradas pelo Hermes no vault."""
    synthesis_path = VAULT_PATH / "synthesis"
    if not synthesis_path.exists():
        return {"synthesis": [], "message": "Directório de sínteses ainda não existe."}

    cutoff = time.time() - days * 86400
    files = glob.glob(str(synthesis_path / "*.md"))
    recent = []

    for file_path in files:
        if Path(file_path).stat().st_mtime >= cutoff:
            data = await read_md_file(Path(file_path))
            recent.append({
                "file": Path(file_path).name,
                "preview": data["content"][:500],
                "frontmatter": data["frontmatter"],
            })

    recent.sort(key=lambda x: x["file"], reverse=True)
    return {"days": days, "synthesis": recent, "total": len(recent)}


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=3100, reload=False)
