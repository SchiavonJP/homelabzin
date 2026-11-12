"""Bounded public text capture. DNS is validated and the connection pinned to that IP."""
import http.client
import ipaddress
import re
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, urljoin, quote

from app.vault import DomainError, MAX_CAPTURE


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts, self.main, self.title = [], [], []
        self.main_depth = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','nav','footer','header','form','noscript','svg','template'):
            self.skip += 1
        if tag in ('article','main'):
            self.main_depth += 1
        if tag == 'title': self.in_title = True
        if tag in ('p','h1','h2','h3','li','br','pre'):
            self.parts.append('\n'); self.main.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script','style','nav','footer','header','form','noscript','svg','template'):
            self.skip = max(0, self.skip - 1)
        if tag in ('article','main'): self.main_depth = max(0, self.main_depth - 1)
        if tag == 'title': self.in_title = False

    def handle_data(self, data):
        if self.in_title: self.title.append(data)
        if not self.skip:
            self.parts.append(data)
            if self.main_depth: self.main.append(data)

    def text(self):
        value = ''.join(self.main) if ''.join(self.main).strip() else ''.join(self.parts)
        return re.sub(r'[ \t]+', ' ', re.sub(r'\n\s*\n+', '\n\n', value)).strip()


def public_url(value):
    try:
        p = urlsplit(value)
        if (len(value) > 4096 or any(ord(c) < 33 for c in value) or '\\' in value
                or p.scheme not in ('https','http') or not p.hostname or p.username or p.password
                or p.port not in (None,443 if p.scheme == 'https' else 80)):
            raise ValueError()
        host = p.hostname.encode('idna').decode().lower()
        if not re.fullmatch(r'[a-z0-9.-]+', host) or '.' not in host or host.endswith('.'):
            raise ValueError()
        return urlunsplit((p.scheme, host, quote(p.path or '/',safe="/:@!$&'()*+,;=%-._~"), quote(p.query,safe=":@!$&'()*+,;=/%?-._~"), ''))
    except (ValueError, UnicodeError):
        raise DomainError('reference_url_invalid', 422) from None


def public_addresses(host, port):
    try:
        addresses = list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)))
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise DomainError('article_private_destination', 422)
        return addresses
    except (OSError, ValueError):
        raise DomainError('article_dns_unavailable', 503) from None


def fetch_article(url, domains):
    url = public_url(url)
    for _ in range(4):
        p = urlsplit(url)
        if p.scheme != 'https' or p.hostname not in domains:
            raise DomainError('article_domain_not_approved', 422)
        addresses = public_addresses(p.hostname,443)
        connection = http.client.HTTPSConnection(p.hostname,443,timeout=20,context=ssl.create_default_context())
        # HTTPSConnection wraps the pinned socket using the original hostname/SNI.
        connection._create_connection = lambda address, timeout, source_address=None: socket.create_connection((addresses[0],443),timeout,source_address)
        try:
            connection.request('GET',urlunsplit(('', '', p.path, p.query, '')),
                               headers={'User-Agent':'Xereta/0.6 reference capture','Accept':'text/html,text/plain','Accept-Encoding':'identity'})
            response = connection.getresponse()
            if response.status in (301,302,303,307,308):
                location = response.getheader('Location')
                if not location: raise DomainError('article_redirect_invalid',422)
                url = public_url(urljoin(url, location)); continue
            if response.status != 200: raise DomainError('article_unavailable',422)
            content_type = response.getheader('Content-Type','').split(';')[0].strip()
            if content_type not in ('text/html','text/plain','application/xhtml+xml'):
                raise DomainError('article_type_unsupported',422)
            if response.getheader('Content-Encoding','identity') not in ('','identity'):
                raise DomainError('article_encoding_unsupported',422)
            raw = response.read(MAX_CAPTURE+1)
            if len(raw)>MAX_CAPTURE: raise DomainError('article_too_large',422)
            try: text = raw.decode('utf-8-sig')
            except UnicodeError: raise DomainError('article_encoding_unsupported',422) from None
            parser=ArticleText();parser.feed(text)
            body=parser.text() if content_type != 'text/plain' else text.strip()
            if len(body)<120: raise DomainError('article_capture_incomplete',422)
            return {'title': ''.join(parser.title).strip()[:500], 'body':body,'url':url}
        except (OSError,http.client.HTTPException):
            raise DomainError('article_fetch_unavailable',503) from None
        finally: connection.close()
    raise DomainError('article_redirect_limit',422)
