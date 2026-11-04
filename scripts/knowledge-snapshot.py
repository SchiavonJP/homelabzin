#!/usr/bin/env python3
"""Create a bounded, persistent Markdown pilot for AFFiNE's Obsidian importer.

Reads the source without changing it. The default requires the verified live
SSHFS mount; --source-kind directory supports an existing local copy instead.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import unicodedata
from urllib.parse import quote
import zipfile


MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_NOTES = 249  # AFFiNE web limit is 250 documents, including our index.
EXPECTED_SOURCE = "schiva@100.80.3.58:/home/schiva/Documentos/Obsidian Vault"


class SnapshotError(Exception):
    pass


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def verify_source(source, kind):
    if not source.is_dir():
        raise SnapshotError("Source directory is unavailable.")
    if kind == "directory":
        return {"kind": kind, "path": str(source), "mount_verified": False}
    try:
        result = subprocess.run(
            ["findmnt", "--json", "--target", str(source)],
            capture_output=True, text=True, timeout=10, check=True,
        )
        entries = json.loads(result.stdout).get("filesystems", [])
    except (OSError, ValueError, subprocess.SubprocessError):
        raise SnapshotError("Cannot verify SSHFS mount. Inspect it on sb-hermes first.") from None
    if not entries or entries[0].get("fstype") != "fuse.sshfs":
        raise SnapshotError("Source is not mounted through SSHFS; refusing to export an underlying local directory.")
    mount = entries[0]
    if mount.get("source") != EXPECTED_SOURCE or Path(mount.get("target", "")).resolve() != source:
        raise SnapshotError("Mount identity differs from the verified notebook vault; inspect it before exporting.")
    return {"kind": kind, "path": str(source), "mount_verified": True,
            "mount_source": mount["source"], "fstype": mount["fstype"]}


def markdown_files(source):
    files = []

    def fail(error):
        raise error

    for root, dirs, names in os.walk(source, followlinks=False, onerror=fail):
        root = Path(root)
        dirs[:] = sorted(name for name in dirs if not name.startswith(".")
                         and name != "_AgentKnowledge" and not (root / name).is_symlink())
        for name in sorted(names):
            path = root / name
            if name.startswith(".") or path.suffix.lower() != ".md" or path.is_symlink():
                continue
            if not path.is_file():
                continue
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(source).as_posix())


def capture(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_ENTRY_BYTES:
            raise SnapshotError("A selected note exceeds the web import file limit or is not a regular file.")
        data = handle.read(MAX_ENTRY_BYTES + 1)
        after = os.fstat(handle.fileno())
    current = path.stat(follow_symlinks=False)
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if identity(before) != identity(after) or identity(after) != identity(current):
        raise SnapshotError("A note changed during capture; rerun after editing/sync finishes.")
    if len(data) > MAX_ENTRY_BYTES:
        raise SnapshotError("A selected note exceeds the web import file limit.")
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SnapshotError("A selected note is not UTF-8 Markdown.") from None
    return data, before.st_mtime_ns


def path_key(path):
    return unicodedata.normalize("NFC", path).casefold()


def index_markdown(records, captured_at, available):
    lines = ["---", "generated: true", "source_kind: projection", "---", "",
             "# Knowledge pilot snapshot", "", f"Captured: {captured_at}",
             f"Notes: {len(records)} selected from {available} available Markdown files.", "",
             "This is a manual snapshot. Edits in AFFiNE do not synchronize back to Obsidian.",
             "Media and attachments are not included in this Markdown-only pilot.",
             "Links to notes outside the selected pilot may remain unresolved.", "", "## Notes", ""]
    for record in records:
        relative = record["snapshot_path"]
        target = relative[:-3]
        label = record["original_relative_path"].replace("\n", " ").replace("\r", " ")
        if not any(char in target for char in "[]|\n\r"):
            lines.append(f"- [[{target}|{label.replace('|', '／')}]]")
        else:
            label = label.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
            lines.append(f"- [{label}]({quote(relative, safe='/')})")
    return ("\n".join(lines) + "\n").encode("utf-8")


def create_snapshot(source, output, limit=30, source_kind="sshfs"):
    source, output = Path(source).resolve(), Path(output).absolute()
    if not 1 <= limit <= MAX_NOTES:
        raise SnapshotError(f"Pilot limit must be between 1 and {MAX_NOTES} notes.")
    if output.exists() or output.is_symlink():
        raise SnapshotError("Output already exists; choose a new snapshot directory.")
    if output.resolve().is_relative_to(source):
        raise SnapshotError("Output must be outside the source vault.")
    origin = verify_source(source, source_kind)
    started = utc_now()
    available = markdown_files(source)
    if not available:
        raise SnapshotError("No Markdown notes were found; refusing to create an empty pilot.")
    selected = available[:limit]
    records = []
    captured = []
    keys = set()
    total = 0
    for path in selected:
        relative = path.relative_to(source).as_posix()
        snapshot_path = Path(relative).with_suffix(".md").as_posix()
        key = path_key(snapshot_path)
        if key in keys:
            raise SnapshotError("Selected paths collide after case/Unicode normalization; narrow the pilot selection.")
        keys.add(key)
        data, mtime_ns = capture(path)
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise SnapshotError("Pilot exceeds AFFiNE's 32 MiB web limit; choose fewer notes.")
        records.append({"original_relative_path": relative, "snapshot_path": snapshot_path,
                        "bytes": len(data), "source_mtime_ns": mtime_ns,
                        "sha256": hashlib.sha256(data).hexdigest()})
        captured.append(data)
    index_name = "Knowledge Pilot Index.md"
    counter = 2
    while path_key(index_name) in keys:
        index_name = f"Knowledge Pilot Index {counter}.md"
        counter += 1
    index = index_markdown(records, started, len(available))
    total += len(index)
    if len(index) > MAX_ENTRY_BYTES or total > MAX_TOTAL_BYTES:
        raise SnapshotError("Pilot plus index exceeds AFFiNE's browser import limits.")
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < 2 * total + 64 * 1024 * 1024:
        raise SnapshotError("Not enough free space for the folder, ZIP, and a 64 MiB reserve.")
    output.mkdir(mode=0o700)
    try:
        vault = output / "vault"
        vault.mkdir(mode=0o700)
        for record, data in zip(records, captured):
            target = vault / record["snapshot_path"]
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_bytes(data)
            target.chmod(0o600)
        (vault / index_name).write_bytes(index)
        (vault / index_name).chmod(0o600)
        archive = output / "affine-pilot.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(vault.rglob("*.md")):
                bundle.write(path, path.relative_to(output).as_posix())
        archive.chmod(0o600)
        if archive.stat().st_size > MAX_TOTAL_BYTES:
            raise SnapshotError("ZIP exceeds AFFiNE's browser import limit.")
        with zipfile.ZipFile(archive) as bundle:
            if bundle.testzip() is not None:
                raise SnapshotError("ZIP verification failed.")
            for record in records:
                data = bundle.read("vault/" + record["snapshot_path"])
                if hashlib.sha256(data).hexdigest() != record["sha256"]:
                    raise SnapshotError("ZIP note hash verification failed.")
        manifest = {
            "format_version": 1, "complete": True, "sync_mode": "manual_snapshot",
            "capture_started_at": started, "capture_completed_at": utc_now(), "source": origin,
            "notes_available": len(available), "notes_copied": len(records), "selection_limit": limit,
            "selection": "relative path order; hidden/configuration and generated directories excluded",
            "files": records, "generated_index": {"path": index_name, "source_kind": "projection",
                "sha256": hashlib.sha256(index).hexdigest()},
            "media_included": False, "affine_import_verified": False,
            "archive": {"path": archive.name, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()},
            "import": "Extract the ZIP on the computer running AFFiNE; choose Import > Obsidian and select the vault folder.",
        }
        manifest_path = output / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest_path.chmod(0o600)
        return {"status": "snapshot_created", "output": str(output),
                "notes_available": len(available), "notes_copied": len(records),
                "archive": str(archive), "manifest": str(manifest_path),
                "media_included": False, "affine_import_verified": False}
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="/mnt/obsidian-vault")
    parser.add_argument("--source-kind", choices=["sshfs", "directory"], default="sshfs")
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    try:
        report = create_snapshot(args.source, args.output, args.limit, args.source_kind)
    except (SnapshotError, OSError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
