"""Proxmox-only acceptance backup: restore Hindsight into a fresh disposable DB."""
import argparse
import hashlib
import json
import re
import subprocess
from uuid import uuid4


def execute(args, data=None):
    r = subprocess.run(args, input=data, capture_output=True)
    if r.returncode:
        raise RuntimeError("backup_or_restore_command_failed")
    return r.stdout


parser = argparse.ArgumentParser()
parser.add_argument("--database", choices=["knowledge_pilot", "knowledge_curator"], default="knowledge_pilot")
args = parser.parse_args()
source_database = args.database
prefix = ["pct", "exec", "104", "--"]
psql = prefix + ["docker", "exec", "-i", "sb_postgres", "sh", "-c",
                'psql -At -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"', "--"]
dump_path = "/root/xereta-" + source_database + "-" + uuid4().hex[:12] + ".dump"
execute(prefix + ["sh", "-c", 'umask 077; docker exec sb_postgres sh -c \'pg_dump -U "$POSTGRES_USER" -Fc ' + source_database + '\' > '+dump_path])
restore = "xereta_restore_" + uuid4().hex[:12]
execute(psql + ["postgres"], ("CREATE DATABASE " + restore + ";").encode())
execute(prefix + ["sh", "-c", 'docker exec -i sb_postgres sh -c \'pg_restore -U "$POSTGRES_USER" --no-owner --no-privileges --no-comments --exit-on-error -d '+restore+'\' < '+dump_path])


def hashes(db):
    tables = execute(psql + [db], b"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;").decode().splitlines()
    result = {}
    for name in tables:
        if not re.fullmatch(r"[a-zA-Z0-9_]+", name):
            raise RuntimeError("unexpected_table_identifier")
        query = 'SELECT count(*),md5(coalesce(string_agg(to_jsonb(t)::text,\'\' ORDER BY to_jsonb(t)::text),\'\')) FROM public."'+name+'" t;'
        result[name] = execute(psql + [db], query.encode()).decode().strip()
    return result


original, restored = hashes(source_database), hashes(restore)
if original != restored:
    raise RuntimeError("restore_hash_mismatch")
report = {"status": "restore_verified", "source_database": source_database, "database": restore, "dump_path": dump_path, "tables_checked": len(original), "row_digests": original}
print(json.dumps(report))
