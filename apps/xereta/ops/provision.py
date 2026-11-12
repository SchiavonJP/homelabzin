"""Run on Proxmox: private bootstrap and recovery checks; never prints credentials.

Targets only the new Xereta role/database and disposable restore database.
Existing LiveSync, vault, Hermes provider and MCP containers are not modified.
"""
import json
import subprocess
import sys


def run(args, body=None):
    result = subprocess.run(args, input=body, text=True, capture_output=True)
    if result.returncode:
        print(json.dumps({"status": "failed", "step": args[0:4], "exit": result.returncode}))
        sys.exit(1)
    return result.stdout


def guest(ct, code):
    return run(["pct", "exec", str(ct), "--", "python3", "-"], code)


configuration = guest(107, r'''
import json,os,secrets
from pathlib import Path
os.umask(0o077)
root=Path('/root/xereta');root.mkdir(exist_ok=True,mode=0o700)
destination=root/'.env'
if not destination.exists():
    old={}
    for line in Path('/root/knowledge-hindsight-pilot/.env').read_text().splitlines():
        key,sep,value=line.partition('=')
        if sep:old[key]=value.strip().strip('"\'')
    dbpass=secrets.token_urlsafe(36)
    cfg={'XERETA_DATABASE_URL':'postgresql+psycopg://xereta:'+dbpass+'@192.168.0.210:5432/knowledge_curator',
         'XERETA_SECRET_KEY':secrets.token_urlsafe(64),'XERETA_OWNER_EMAIL':'owner@xereta.local',
         'XERETA_OWNER_PASSWORD':secrets.token_urlsafe(24),'XERETA_AGENT_READ_TOKEN':secrets.token_urlsafe(48),
         'XERETA_LITELLM_KEY':old['HINDSIGHT_API_LLM_API_KEY'],'XERETA_STATE_PATH':'/data',
         'XERETA_HINDSIGHT_BANK':'knowledge-vault-pilot','XERETA_PUBLISH_ENABLED':'false',
         'XERETA_ACCEPTANCE_PASSED':'false'}
    destination.write_text('\n'.join(k+'='+v for k,v in cfg.items())+'\n')
    (root/'owner-login.json').write_text(json.dumps({'email':cfg['XERETA_OWNER_EMAIL'],'password':cfg['XERETA_OWNER_PASSWORD']}))
    (root/'db-password').write_text(dbpass)
print(json.dumps({'password':(root/'db-password').read_text()}))
''')
password = json.loads(configuration)["password"]
# URL-safe randomly generated password; never interpolates input from an HTTP caller.
assert all(c.isalnum() or c in "_-" for c in password)
sql = r"""DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='xereta') THEN
CREATE ROLE xereta LOGIN PASSWORD '%s' NOSUPERUSER NOCREATEDB NOCREATEROLE;
END IF; END $$;
SELECT 'CREATE DATABASE knowledge_curator OWNER xereta' WHERE NOT EXISTS
(SELECT FROM pg_database WHERE datname='knowledge_curator')\gexec
""" % password
run(["pct", "exec", "104", "--", "docker", "exec", "-i", "sb_postgres", "sh", "-c",
     'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres'], sql)
print(json.dumps({"database": "knowledge_curator", "role": "xereta", "status": "provisioned"}))

guest(107, r'''
import os,subprocess
from pathlib import Path
os.umask(0o077)
root=Path('/root/xereta/rollback');root.mkdir(exist_ok=True)
for name in ('sb_mcp','sb_hermes','sb_hindsight_pilot'):
    r=subprocess.run(['docker','inspect',name],capture_output=True,check=True)
    (root/(name+'.json')).write_bytes(r.stdout)
subprocess.run(['docker','cp','sb_mcp:/app/server.py',str(root/'legacy-server.py')],check=True,capture_output=True)
''')
print(json.dumps({"rollback": "saved", "existing_services": "unchanged"}))
