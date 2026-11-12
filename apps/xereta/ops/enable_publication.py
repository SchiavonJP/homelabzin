"""Run on Hermes only after the live CAS gate passes in this session."""
import os
from pathlib import Path
os.umask(0o077)
p=Path('/root/xereta/.env')
s=p.read_text()
assert 'XERETA_PUBLISH_ENABLED=false' in s or 'XERETA_PUBLISH_ENABLED=true' in s
new=p.with_name('.env.next')
new.write_text(s.replace('XERETA_PUBLISH_ENABLED=false','XERETA_PUBLISH_ENABLED=true'))
new.chmod(0o600);new.replace(p)
print('publication_enabled_scheduling_unchanged')
