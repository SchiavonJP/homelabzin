'use strict';
// Runs in AFFiNE's exact pinned image, with no database or Docker credentials.
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const crypto=require('node:crypto');
const {createRequire}=require('node:module');
const codec=require('../../../scripts/knowledge-affine-reader.cjs');
const LIMIT=8*1024*1024;
const validId=x=>typeof x==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(x);
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const fail=code=>{throw Object.assign(new Error(code),{safeCode:code})};
const NATIVE={'x-affine-client-kind':'native'};

async function bounded(response,limit=LIMIT){
 const chunks=[];let length=0;
 for await(const chunk of response.body){length+=chunk.length;if(length>limit)fail('response_too_large');chunks.push(chunk)}
 return Buffer.concat(chunks);
}
function readPrivate(file){
 const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
 try{const st=fs.fstatSync(fd);if(!st.isFile()||(st.mode&0o077)||st.size>65536)fail('invalid_private_file');return fs.readFileSync(fd,'utf8')}
 finally{fs.closeSync(fd)}
}
function atomic(file,value){
 const temporary=path.join(path.dirname(file),'.'+crypto.randomUUID());
 const fd=fs.openSync(temporary,'wx',0o600);
 try{fs.writeFileSync(fd,JSON.stringify(value));fs.fsyncSync(fd)}finally{fs.closeSync(fd)}
 fs.renameSync(temporary,file);
 const dir=fs.openSync(path.dirname(file),'r');try{fs.fsyncSync(dir)}finally{fs.closeSync(dir)}
}
class Session{
 constructor(file,fetcher=fetch){this.file=file;this.fetch=fetcher}
 async token(){
  let s=JSON.parse(readPrivate(this.file));
  if(s.origin!=='http://127.0.0.1:3010'||typeof s.accessToken!=='string'||typeof s.refreshToken!=='string')fail('reauth_required');
  if(Date.now()+60000>=s.expiresAt){
   // A durable intent prevents blindly replaying a one-use refresh after death.
   if(s.refreshPending)fail('reauth_required');
   atomic(this.file,{...s,refreshPending:true});
   let response;
   try{response=await this.fetch(s.origin+'/api/auth/session/refresh',{method:'POST',redirect:'error',
     headers:{...NATIVE,'Content-Type':'application/json'},body:JSON.stringify({refreshToken:s.refreshToken}),signal:AbortSignal.timeout(20000)})}
   catch{fail('reauth_required')}
   if(!response.ok)fail('reauth_required');
   const value=JSON.parse((await bounded(response,65536)).toString());
   if(typeof value.accessToken!=='string'||typeof value.refreshToken!=='string'||!Number.isFinite(value.expiresIn)||value.expiresIn<=0)fail('reauth_required');
   s={...value,origin:s.origin,expiresAt:Date.now()+value.expiresIn*1000,refreshPending:false};atomic(this.file,s);
  }
  if(s.refreshPending)fail('reauth_required');
  return s.accessToken;
 }
}
class Reader{
 constructor(state,config,options={}){
  this.state=state;this.config=config;this.fetch=options.fetch||fetch;
  this.session=options.session||new Session(path.join(state,'auth.json'),this.fetch);
  this.native=options.native;this.Y=options.Y;
 }
 workspace(id){if(!validId(id)||!this.config.workspaces.includes(id))fail('workspace_not_allowed')}
 async request(route,body){
  const token=await this.session.token();
  const r=await this.fetch('http://127.0.0.1:3010'+route,{method:body?'POST':'GET',redirect:'error',
   headers:{...NATIVE,Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},
   ...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(30000)});
  if(r.status===401||r.status===403)fail('reauth_required');
  if(r.status===404)fail('document_missing');
  if(!r.ok)fail('affine_unavailable');
  return r;
 }
 async graphql(query,variables){
  const r=await this.request('/graphql',{query,variables});
  const value=JSON.parse((await bounded(r)).toString());
  if(value.errors?.length||!value.data)fail('affine_graphql_failed');
  return value.data;
 }
 async inventory(workspace,after=null){
  this.workspace(workspace);if(after!==null&&(typeof after!=='string'||after.length>2048))fail('invalid_cursor');
  const data=await this.graphql('query($id:String!,$page:PaginationInput!){workspace(id:$id){recentlyUpdatedDocs(pagination:$page){edges{node{id title updatedAt}} pageInfo{hasNextPage endCursor} totalCount}}}',{id:workspace,page:{first:100,...(after?{after}:{})}});
  const docs=data.workspace?.recentlyUpdatedDocs;
  if(!docs||!Array.isArray(docs.edges)||!docs.pageInfo)fail('invalid_inventory');
  const excluded=new Set(this.config.generated?.[workspace]||[]);
  return {items:docs.edges.map(e=>e.node).filter(n=>validId(n.id)&&!excluded.has(n.id)&&!String(n.title||'').startsWith('_AgentKnowledge')).map(n=>({id:n.id,title:n.title||'',updated_at:n.updatedAt})),
    complete:!docs.pageInfo.hasNextPage,cursor:docs.pageInfo.endCursor,total:docs.totalCount};
 }
 async capture(workspace,document){
  this.workspace(workspace);if(!validId(document))fail('invalid_document');
  if((this.config.generated?.[workspace]||[]).includes(document))fail('generated_source_excluded');
  const version=await this.graphql('query{serverConfig{version}}',{});
  if(version.serverConfig?.version!=='0.27.4')fail('codec_version_mismatch');
  const r=await this.request('/api/workspaces/'+workspace+'/docs/'+document);
  if(!(r.headers.get('content-type')||'').includes('application/octet-stream'))fail('not_a_snapshot');
  const bytes=await bounded(r);const requireNative=createRequire('/app/package.json');
  const Y=this.Y||requireNative('yjs'),native=this.native||requireNative('/app/dist/server-native.x64.node');
  const decoded=codec.decoded(native,bytes,{id:document,acceptNoteContainer:true,acceptEmptySurface:true},
    'https://affine.joaopaulo.me/workspace/'+workspace,codec.inspectLayout(bytes,Y));
  if(Buffer.byteLength(decoded.markdown)>LIMIT)fail('response_too_large');
  const generated=/^generated:\s*true\s*$/m.test(decoded.markdown.slice(0,1000))||decoded.title.startsWith('_AgentKnowledge');
  const dir=path.join(this.state,'captures',workspace,document);fs.mkdirSync(dir,{recursive:true,mode:0o700});
  const hashed=sha(bytes),archive=path.join(dir,hashed+'.bin');
  try{fs.writeFileSync(archive,bytes,{flag:'wx',mode:0o600})}catch(e){if(e.code!=='EEXIST')throw e;if(sha(fs.readFileSync(archive))!==hashed)fail('archive_integrity_failed')}
  const warnings=[...decoded.knownUnsupportedBlocks,...decoded.unknownBlocks];
  const complete=decoded.complete&&!generated;
  atomic(path.join(dir,hashed+'.json'),{complete,title:decoded.title,warnings,acceptedWarnings:decoded.acceptedWarnings,capturedAt:new Date().toISOString()});
  return {complete,reason:generated?'generated_source_excluded':complete?'':'capture_incomplete',warnings,
    ...(complete?{title:decoded.title,body:decoded.markdown,snapshot:bytes.toString('base64'),snapshot_sha256:hashed,markdown_sha256:sha(decoded.markdown)}:{})};
 }
}
function authenticated(header,key){
 if(typeof header!=='string'||header.length>512||!header.startsWith('Bearer '))return false;
 return crypto.timingSafeEqual(crypto.createHash('sha256').update(header.slice(7)).digest(),crypto.createHash('sha256').update(key).digest());
}
function server(reader,key){
 let queue=Promise.resolve();
 const app=http.createServer(async(req,res)=>{
  const send=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(data))};
  if(!['127.0.0.1','192.168.0.213','192.168.0.221'].includes((req.socket.remoteAddress||'').replace(/^::ffff:/,'')))return send(403,{error:'source_not_allowed'});
  if(req.method==='GET'&&req.url==='/health/live')return send(200,{status:'ok'});
  if(!authenticated(req.headers.authorization,key))return send(401,{error:'authentication_required'});
  if(req.method!=='POST'||!['/inventory','/capture','/status'].includes(req.url))return send(404,{error:'not_found'});
  let size=0,chunks=[];
  try{for await(const chunk of req){size+=chunk.length;if(size>16384)fail('request_too_large');chunks.push(chunk)}}catch{return send(413,{error:'invalid_request'})}
  let body;try{body=JSON.parse(Buffer.concat(chunks).toString());if(!body||Array.isArray(body)||typeof body!=='object')throw 0}catch{return send(400,{error:'invalid_request'})}
  // Capture and refresh are serialized; at most one decoder/token rotation runs.
  const operation=queue.then(async()=>{
   const keys=req.url==='/capture'?['workspace','document']:req.url==='/inventory'?['workspace','after']:[];
   if(Object.keys(body).some(k=>!keys.includes(k)))fail('invalid_request');
   if(req.url==='/inventory')return reader.inventory(body.workspace,body.after??null);
   if(req.url==='/capture')return reader.capture(body.workspace,body.document);
   const verified=JSON.parse((await bounded(await reader.request('/api/auth/session'),65536)).toString());
   if(!verified.user?.id)fail('reauth_required');
   return {state:'healthy',workspaces:reader.config.workspaces};
  });
  queue=operation.catch(()=>{});
  try{send(200,await operation)}catch(e){const code=e.safeCode||'reader_unavailable';send(code==='reauth_required'?403:code==='document_missing'?404:400,{error:code})}
 });
 app.requestTimeout=15000;app.headersTimeout=10000;app.maxConnections=8;
 return app;
}
if(require.main===module){
 process.umask(0o077);
 const state='/state',config=JSON.parse(readPrivate(path.join(state,'config.json'))),key=readPrivate(path.join(state,'reader-token')).trim();
 if(key.length<32||!Array.isArray(config.workspaces)||config.workspaces.some(x=>!validId(x)))throw new Error('invalid_reader_configuration');
 server(new Reader(state,config),key).listen(3012,'192.168.0.221');
}
module.exports={Session,Reader,server,atomic,authenticated,readPrivate};
