import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx

INBOX = "space/_AgentKnowledge/Inbox.md"
REVIEW_INDEX = "space/_AgentKnowledge/Index.md"
MAX_CAPTURE = 8 * 1024 * 1024


class DomainError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def source_path(value):
    p = PurePosixPath(value)
    if (not value.startswith("space/") or p.is_absolute() or "\\" in value
            or any(x in (".", "..", "") or x.startswith(".") for x in value.split("/"))
            or any(ord(x) < 32 for x in value) or len(value) > 1024
            or not value.endswith(".md")):
        raise DomainError("invalid_vault_path", 422)
    return value


def eligible(value):
    try:
        source_path(value)
    except DomainError:
        return False
    parts = value.casefold().split("/")
    return (not any(p in ("_agentknowledge", "library", "repositories", ".obsidian") for p in parts)
            and parts[-1] not in ("config.md", "styles.md")
            and not any("conflict" in p or "sync-conflict" in p for p in parts))


@dataclass
class Capture:
    path: str
    body: str
    hash: str
    etag: str


class Vault:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.client = httpx.Client(base_url=settings.silverbullet_url,
            headers={"Authorization": "Bearer " + settings.silverbullet_token.get_secret_value()}
            if settings.silverbullet_token.get_secret_value() else {},
            timeout=15, follow_redirects=False, trust_env=False, transport=transport)

    def close(self):
        self.client.close()

    def _request(self, method, path, **kwargs):
        getattr(self, 'before_request', lambda: None)()
        try:
            r = self.client.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise DomainError("silverbullet_unavailable", 503) from None
        if r.status_code == 412:
            raise DomainError("vault_revision_conflict")
        if r.status_code == 404:
            raise DomainError("vault_file_missing", 404)
        if r.status_code >= 300:
            raise DomainError("silverbullet_http_" + str(r.status_code), 503)
        return r

    def inventory(self):
        response = self._request("GET", "/.fs")
        if len(response.content) > 4 * 1024 * 1024:
            raise DomainError("inventory_too_large", 503)
        try:
            rows = response.json()
            if not isinstance(rows, list):
                raise ValueError()
            return [{"path": x["name"], "size": x.get("size", 0), "lastModified": x.get("lastModified")} for x in rows
                    if isinstance(x, dict) and isinstance(x.get("name"), str) and eligible(x["name"])]
        except (ValueError, KeyError, TypeError):
            raise DomainError("invalid_vault_inventory", 503) from None

    def capture(self, path):
        source_path(path)
        response = self._request("GET", "/.fs/" + quote(path, safe="/"))
        if len(response.content) > MAX_CAPTURE:
            raise DomainError("capture_too_large", 422)
        try:
            body = response.content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeError:
            raise DomainError("capture_not_utf8", 422) from None
        if not body.strip():
            raise DomainError("empty_capture", 422)
        return Capture(path, body, digest(body), response.headers.get("etag", ""))

    def write_inbox(self, body, etag=None):
        return self._write_conditional(INBOX, body, etag)

    def write_review(self, path, body, etag=None):
        if path != REVIEW_INDEX and not re.fullmatch(
            r"space/_AgentKnowledge/(Perguntas|Conhecimento|Sync)/[a-z0-9-]{1,110}\.md", path
        ):
            raise DomainError("managed_review_path_required", 422)
        return self._write_conditional(path, body, etag)

    def write_library(self,path,body,etag=None):
        if not re.fullmatch(r'space/_AgentKnowledge/(Referências|Tópicos|Projetos|Conceitos)/(index|[a-f0-9-]{24,64})\.md',path):
            raise DomainError('managed_library_path_required',422)
        return self._write_conditional(path,body,etag)

    def create_reference(self,path,body):
        if not re.fullmatch(r'space/Referências/[a-f0-9-]{36}\.md',path):
            raise DomainError('reference_migration_path_required',422)
        return self._write_conditional(path,body,None)

    def _write_conditional(self, path, body, etag=None):
        if not isinstance(body, str) or not body.strip() or len(body.encode()) > 256 * 1024:
            raise DomainError("invalid_review_body", 422)
        headers = {"Content-Type": "text/markdown"}
        if etag:
            if not re.fullmatch(r'"sha256:[a-f0-9]{64}"', etag):
                raise DomainError("revision_hash_required")
            headers["If-Match"] = etag
        else:
            headers["If-None-Match"] = "*"
        self._request("PUT", "/.fs/" + quote(path, safe="/"), content=body.encode(), headers=headers)
        current = self.capture(path)
        if current.body != body:
            raise DomainError("publication_readback_changed")
        return current

    def permalink(self, path):
        source_path(path)
        return self.settings.public_silverbullet_url + "/" + quote(path.removesuffix(".md"), safe="/")
