"""Karakeep 0.33 API; metadata enumeration never requests article content."""
import re
import httpx
from app.vault import DomainError, MAX_CAPTURE


class Karakeep:
    def __init__(self,settings,transport=None):
        self.settings=settings
        self.client=httpx.Client(base_url=settings.karakeep_url+'/api/v1',follow_redirects=False,trust_env=False,
            timeout=20,transport=transport,headers={'Authorization':'Bearer '+settings.karakeep_token.get_secret_value()})

    def close(self):self.client.close()

    @staticmethod
    def identifier(value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value):raise DomainError('karakeep_identity_invalid',422)
        return value

    def call(self,method,path,body=None,params=None):
        try:
            with self.client.stream(method,path,json=body,params=params) as r:
                if r.status_code in (401,403):raise DomainError('karakeep_authentication_required',503)
                if r.status_code>=300:raise DomainError('karakeep_request_failed',503)
                chunks=[];size=0
                for chunk in r.iter_bytes():
                    size+=len(chunk)
                    if size>MAX_CAPTURE:raise DomainError('karakeep_response_too_large',503)
                    chunks.append(chunk)
            import json
            data=json.loads(b''.join(chunks))
            if not isinstance(data,dict):raise ValueError()
            return data
        except httpx.HTTPError:raise DomainError('karakeep_unavailable',503) from None
        except (ValueError,TypeError):raise DomainError('karakeep_invalid_response',503) from None

    def lists(self):
        rows=self.call('GET','/lists').get('lists')
        if not isinstance(rows,list):raise DomainError('karakeep_invalid_response',503)
        return rows

    def page(self,cursor=None,list_id=None):
        route='/lists/'+self.identifier(list_id)+'/bookmarks' if list_id else '/bookmarks'
        data=self.call('GET',route,params={'includeContent':'false','limit':100,**({'cursor':cursor} if cursor else {})})
        if not isinstance(data.get('bookmarks'),list):raise DomainError('karakeep_invalid_response',503)
        next_cursor=data.get('nextCursor')
        if next_cursor is not None and (not isinstance(next_cursor,str) or not next_cursor or next_cursor==cursor):
            raise DomainError('karakeep_invalid_cursor',503)
        return data['bookmarks'],next_cursor

    def require_manual(self,list_id):
        item=next((x for x in self.lists() if x.get('id')==list_id),None)
        if not item or item.get('type')!='manual' or item.get('public') is not False or item.get('hasCollaborators') is not False or item.get('userRole')!='owner':raise DomainError('karakeep_private_manual_list_required',422)

    def is_ready(self,bookmark_id,list_id):
        if not list_id:return False
        self.require_manual(list_id)
        rows=self.call('GET','/bookmarks/'+self.identifier(bookmark_id)+'/lists').get('lists',[])
        return any(x.get('id')==list_id and x.get('type')=='manual' for x in rows)

    def capture(self,bookmark_id):
        data=self.call('GET','/bookmarks/'+self.identifier(bookmark_id),params={'includeContent':'true'})
        content=data.get('content',{})
        if content.get('type')!='link' or content.get('crawlStatus')!='success' or not content.get('htmlContent'):
            raise DomainError('karakeep_article_incomplete',422)
        from app.article_reader import ArticleText
        parser=ArticleText();parser.feed(content['htmlContent']);text=parser.text()
        if len(text)<120:raise DomainError('karakeep_article_incomplete',422)
        highlights=self.call('GET','/bookmarks/'+self.identifier(bookmark_id)+'/highlights').get('highlights',[])
        annotations='\n\n'.join([str(data.get('note') or ''),*[str(x.get('text') or '') for x in highlights]]).strip()
        return {'title':data.get('title') or content.get('title') or '', 'body':text,'url':content['url'],'annotations':annotations}

    def create_bookmark(self,url,title,note):
        existing=self.call('GET','/bookmarks/check-url',params={'url':url}).get('bookmarkId')
        if existing:return {'id':self.identifier(existing),'reused':True}
        return self.call('POST','/bookmarks',{'type':'link','url':url,'title':title,'note':note,'source':'api'})

    def add_to_inbox(self,bookmark_id,list_id):
        self.require_manual(list_id)
        return self.call('PUT','/lists/'+self.identifier(list_id)+'/bookmarks/'+self.identifier(bookmark_id))
