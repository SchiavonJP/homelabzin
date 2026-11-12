'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {Session,Reader,server,authenticated,atomic}=require('./service.cjs');
function fixture(){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'xereta-affine-'));return {dir,file:path.join(dir,'auth.json'),clean:()=>fs.rmSync(dir,{recursive:true,force:true})}}
const pair={origin:'http://127.0.0.1:3010',accessToken:'synthetic-access',refreshToken:'synthetic-refresh',expiresAt:1,refreshPending:false};

test('refresh rotates and atomically persists the session without passwords',async()=>{
 const f=fixture();let calls=0;
 try{atomic(f.file,pair);const s=new Session(f.file,async(url,options)=>{
  calls++;assert.equal(url,'http://127.0.0.1:3010/api/auth/session/refresh');
  assert.equal(options.redirect,'error');assert.equal(options.headers['x-affine-client-kind'],'native');
  return new Response(JSON.stringify({accessToken:'new-access',refreshToken:'new-refresh',expiresIn:3600}));
 });assert.equal(await s.token(),'new-access');assert.equal(await s.token(),'new-access');assert.equal(calls,1);
 const stored=JSON.parse(fs.readFileSync(f.file));assert.equal(stored.refreshToken,'new-refresh');assert.equal(stored.refreshPending,false);
 assert.equal(fs.statSync(f.file).mode&0o777,0o600);assert.equal(JSON.stringify(stored).includes('password'),false);
 }finally{f.clean()}
});

test('ambiguous refresh is held across process restart and never blindly replayed',async()=>{
 const f=fixture();let calls=0;
 try{atomic(f.file,pair);const s=new Session(f.file,async()=>{calls++;throw new Error('private transport body')});
 await assert.rejects(s.token(),/reauth_required/);
 const restarted=new Session(f.file,async()=>{calls++;assert.fail('one-use token replay')});
 await assert.rejects(restarted.token(),/reauth_required/);assert.equal(calls,1);
 }finally{f.clean()}
});

test('session files must be private and origin bound',async()=>{
 const f=fixture();try{
 atomic(f.file,{...pair,origin:'https://evil.invalid'});await assert.rejects(new Session(f.file).token(),/reauth_required/);
 atomic(f.file,pair);fs.chmodSync(f.file,0o644);await assert.rejects(new Session(f.file).token(),/invalid_private_file/);
 }finally{f.clean()}
});

test('inventory stays metadata-only, paginates and excludes known generated IDs',async()=>{
 const f=fixture();let requests=[];
 const reader=new Reader(f.dir,{workspaces:['workspace'],generated:{workspace:['generated']}},{session:{token:async()=>'synthetic'},fetch:async(url,options)=>{
  requests.push({url,body:JSON.parse(options.body)});
  return new Response(JSON.stringify({data:{workspace:{recentlyUpdatedDocs:{edges:[{node:{id:'note',title:'Note',updatedAt:'v1'}},{node:{id:'generated',title:'Index',updatedAt:'v1'}}],pageInfo:{hasNextPage:true,endCursor:'next'},totalCount:2}}}}));
 }});
 try{const result=await reader.inventory('workspace');assert.deepEqual(result.items,[{id:'note',title:'Note',updated_at:'v1'}]);assert.equal(result.cursor,'next');assert.equal(result.complete,false);
 assert.equal(requests.length,1);assert.equal(requests[0].url,'http://127.0.0.1:3010/graphql');assert.equal(requests[0].body.variables.page.first,100);
 await assert.rejects(reader.inventory('other'),/workspace_not_allowed/);await assert.rejects(reader.capture('workspace','../escape'),/invalid_document/);assert.equal(requests.length,1);
 }finally{f.clean()}
});

test('HTTP bridge requires its own bearer, has no arbitrary URL endpoint and serializes reads',async()=>{
 const key='synthetic-bridge-key-with-32-characters';let active=0,max=0;
 const app=server({inventory:async()=>{active++;max=Math.max(max,active);await new Promise(r=>setTimeout(r,5));active--;return {items:[],complete:true}},config:{workspaces:['workspace']}},key);
 await new Promise(r=>app.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+app.address().port;
 try{
  assert.equal((await fetch(base+'/health/live')).status,200);
  assert.equal((await fetch(base+'/inventory',{method:'POST',body:'{}'})).status,401);
  const headers={Authorization:'Bearer '+key,'Content-Type':'application/json'};
  const bad=await fetch(base+'/inventory',{method:'POST',headers,body:JSON.stringify({url:'https://evil.invalid'})});assert.equal(bad.status,400);
  await Promise.all([1,2].map(()=>fetch(base+'/inventory',{method:'POST',headers,body:JSON.stringify({workspace:'workspace'})})));
  assert.equal(max,1);assert.equal(authenticated('Bearer wrong',key),false);
 }finally{app.closeAllConnections();await new Promise(r=>app.close(r))}
});
