"""Provision a distinct refreshable session on CT106 from an existing private cookie.

No password is read or saved. Output is never printed. Run locally on the AFFiNE
machine; pass a NEW mode-0600 output filename, then replace the reader's auth.json.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import urllib.request
from uuid import uuid4

BASE = 'http://127.0.0.1:3010'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def provision(cookie_file, output):
    fd = os.open(cookie_file, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 65536:
            raise ValueError('invalid_private_file')
        cookie = json.load(f)
    if cookie.get('origin') != BASE or not isinstance(cookie.get('cookie'), str):
        raise ValueError('invalid_session_origin')
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))
    def call(route, data=None, headers=None):
        request = urllib.request.Request(BASE + route, json.dumps(data).encode() if data is not None else None,
            {'Content-Type': 'application/json', 'x-affine-client-kind': 'native', **(headers or {})})
        with opener.open(request, timeout=20) as r:
            payload = r.read(65537)
            if len(payload) > 65536:
                raise ValueError('invalid_auth_response')
            return json.loads(payload)
    code = call('/api/auth/open-app/sign-in-code', {}, {'Cookie': cookie['cookie']})
    if not isinstance(code.get('code'), str):
        raise ValueError('exchange_code_unavailable')
    signed = call('/api/auth/open-app/sign-in', {'code': code['code']})
    pair = call('/api/auth/session/exchange', {'code': signed['exchangeCode'], 'installationId': str(uuid4()),
        'platform': 'electron', 'deviceName': 'Xereta server reader'})
    import time
    if not isinstance(pair.get('accessToken'), str) or not isinstance(pair.get('refreshToken'), str):
        raise ValueError('token_pair_unavailable')
    identity = call('/api/auth/session', headers={'Authorization': 'Bearer ' + pair['accessToken']})
    if not identity.get('user', {}).get('id'):
        raise ValueError('session_verification_failed')
    pair.update(origin=BASE, expiresAt=int(time.time() * 1000) + pair['expiresIn'] * 1000, refreshPending=False)
    dest = Path(output)
    with os.fdopen(os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'w') as f:
        json.dump(pair, f); f.flush(); os.fsync(f.fileno())
    return {'status': 'session_saved', 'password_saved': False, 'session_verified': True}


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cookie-auth-file', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(provision(args.cookie_auth_file, args.output)))
    except Exception:
        print(json.dumps({'status': 'blocked', 'reason': 'session_provision_failed'}))
        raise SystemExit(1)
