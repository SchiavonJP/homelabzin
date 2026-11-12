#!/usr/bin/env python3
"""Interactive AFFiNE password sign-in; save a private session, never the password.

Run on the AFFiNE machine. This uses its normal browser-session endpoints and
does not create an account, change permissions, or send a magic-link email.
"""
import argparse
import getpass
import http.cookies
import json
import os
from pathlib import Path
import sys
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def sign_in(base, email, password, opener=None):
    url=urllib.parse.urlsplit(base)
    if (url.scheme not in ('http','https') or url.netloc not in (
            '127.0.0.1:3010','192.168.0.221:3010','affine.joaopaulo.me')
            or url.path not in ('','/') or url.query or url.fragment or url.username or url.password):
        raise ValueError('invalid_origin')
    if not email or not password:
        raise ValueError('email_and_password_required')
    base=base.rstrip('/')
    opener=opener or urllib.request.build_opener(NoRedirect(),urllib.request.ProxyHandler({}))
    request=urllib.request.Request(base+'/api/auth/sign-in',json.dumps({'email':email,'password':password}).encode(),
        {'Content-Type':'application/json','Accept':'application/json'},method='POST')
    with opener.open(request,timeout=20) as response:
        cookie=http.cookies.SimpleCookie()
        for value in response.headers.get_all('Set-Cookie',[]):
            cookie.load(value)
        encoded='; '.join(k+'='+m.coded_value for k,m in cookie.items() if m.value)
    if not encoded:
        raise ValueError('session_cookie_unavailable')
    # Verify the normal authenticated session before retaining a credential.
    request=urllib.request.Request(base+'/api/auth/session',headers={'Cookie':encoded,'Accept':'application/json'})
    with opener.open(request,timeout=15) as response:
        identity=json.loads(response.read(65536))
        if not isinstance(identity,dict) or not isinstance(identity.get('user'),dict) or not identity['user'].get('id'):
            raise ValueError('session_verification_failed')
    return {'origin':base,'cookie':encoded,'refresh':'interactive_sign_in_when_expired'}


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',default='http://127.0.0.1:3010')
    p.add_argument('--output',required=True)
    args=p.parse_args()
    output=Path(args.output).absolute()
    if output.exists() or output.is_symlink():
        print(json.dumps({'status':'blocked','reason':'choose_a_new_private_auth_file'}))
        return 1
    try:
        email=input('AFFiNE account email: ').strip()
        password=getpass.getpass('AFFiNE password (not saved): ')
        session=sign_in(args.base_url,email,password)
        output.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
        with os.fdopen(os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:
            json.dump(session,f)
        print(json.dumps({'status':'session_saved','auth_file':str(output),'password_saved':False}))
        return 0
    except (Exception,KeyboardInterrupt):
        print(json.dumps({'status':'blocked','reason':'sign_in_failed_no_password_saved'}))
        return 1


if __name__=='__main__':
    sys.exit(main())
