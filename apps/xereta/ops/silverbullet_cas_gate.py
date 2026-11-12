"""Disposable-file gate. Run inside the Xereta container; never touches original notes."""
import json
from urllib.parse import quote
from uuid import uuid4
from app.config import Settings
from app.vault import Vault, digest

cfg = Settings()
vault = Vault(cfg)
path = 'space/_AgentKnowledge/.xereta-cas-' + str(uuid4()) + '.md'
url = '/.fs/' + quote(path, safe='/')
a, b = '# Xereta CAS probe\n\nprimeira versão\n', '# Xereta CAS probe\n\nedição humana simulada\n'
checks = {}
try:
    r=vault.client.put(url,content=a.encode(),headers={'If-None-Match':'*','Content-Type':'text/markdown'})
    checks['create']=r.status_code in (200,201,204)
    r=vault.client.get(url); etag=r.headers.get('etag','')
    checks['readback']=r.text==a and etag=='"sha256:'+digest(a)+'"'
    checks['duplicate_create_denied']=vault.client.put(url,content=b.encode(),headers={'If-None-Match':'*'}).status_code==412
    checks['conditional_update']=vault.client.put(url,content=b.encode(),headers={'If-Match':etag}).status_code in (200,201,204)
    checks['stale_update_denied']=vault.client.put(url,content=a.encode(),headers={'If-Match':etag}).status_code==412
    checks['edit_preserved']=vault.client.get(url).text==b
finally:
    current=vault.client.get(url)
    if current.status_code==200 and current.text in (a,b):
        checks['cleanup']=vault.client.delete(url,headers={'If-Match':current.headers.get('etag','')}).status_code in (200,204)
    vault.close()
print(json.dumps({'gate':'silverbullet-live-cas','passed':all(checks.values()),'checks':checks}))
if not all(checks.values()):raise SystemExit(1)
