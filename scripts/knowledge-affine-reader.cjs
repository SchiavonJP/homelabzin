#!/usr/bin/env node
/** Run inside the pinned AFFiNE container. No app internals or DB credentials needed.
 * Input: private JSON allowlist {workspace, documents:[{id,title?}]}; max 3 docs.
 * Credentials: AFFINE_COOKIE or AFFINE_TOKEN, supplied outside Git.
 * Output: immutable capture batch, raw snapshots, Markdown, and manifest.
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { createRequire } = require('node:module');
const LIMIT = 8 * 1024 * 1024;
const sha = data => crypto.createHash('sha256').update(data).digest('hex');
const validId = id => typeof id === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(id);

function fail(code) { throw new Error(code); }
function configuration(value, endpoint) {
  const url = new URL(endpoint);
  if (!['http:', 'https:'].includes(url.protocol) ||
      !['127.0.0.1:3010', '192.168.0.221:3010', 'affine.joaopaulo.me'].includes(url.host) ||
      url.username || url.password || url.search || url.hash || url.pathname !== '/') fail('invalid_origin');
  if (!value || !validId(value.workspace) || !Array.isArray(value.documents) ||
      value.documents.length < 1 || value.documents.length > 3 ||
      value.documents.some(d => !validId(d.id)) ||
      new Set(value.documents.map(d=>d.id)).size !== value.documents.length) fail('invalid_allowlist');
  return url.origin;
}

function inspectLayout(bytes, Y) {
  const doc=new Y.Doc();
  Y.applyUpdate(doc,bytes);
  const notes=new Set(), emptySurfaces=new Set();
  for (const [id,block] of doc.getMap('blocks')) {
    if (block.get('sys:flavour')==='affine:note') notes.add(id);
    if (block.get('sys:flavour')!=='affine:surface' || block.get('sys:children')?.length!==0) continue;
    const elements=block.get('prop:elements');
    const empty=elements instanceof Y.Map && (elements.size===0 ||
      (elements.size===2 && elements.has('type') && elements.get('value') instanceof Y.Map && elements.get('value').size===0));
    if (empty && [...block.keys()].every(k=>['sys:id','sys:flavour','sys:version','sys:children','prop:elements'].includes(k)))
      emptySurfaces.add(id);
  }
  doc.destroy();
  return {notes,emptySurfaces};
}

function decoded(native, bytes, document, prefix, layout=null) {
  const value = native.parseDocToMarkdown(bytes, document.id, false, prefix);
  if (!value || typeof value.title !== 'string' || typeof value.markdown !== 'string' ||
      !Array.isArray(value.knownUnsupportedBlocks) || !Array.isArray(value.unknownBlocks)) fail('invalid_decoder_output');
  // The pinned codec flags affine:note layout while preserving its text children.
  // Opt in only for individually export-compared Markdown pilot documents. Keep
  // the original warnings; never waive diagrams, unknown blocks or other types.
  const acceptedWarnings=value.knownUnsupportedBlocks.filter(w=>{
    if (w.endsWith(':affine:note') && document.acceptNoteContainer===true) {
      const locator=w.slice(0,-':affine:note'.length);
      // Imported Yjs block IDs can themselves contain colons. The codec's
      // warning includes that entire ID; suffix matching loses its identity.
      return layout ? layout.notes.has(locator) : w.startsWith('block:'+document.id+':');
    }
    if (w.endsWith(':affine:surface') && document.acceptEmptySurface===true && layout) {
      const locator=w.slice(0,-':affine:surface'.length);
      return layout.emptySurfaces.has(locator);
    }
    return false;
  });
  return { ...value, acceptedWarnings, complete: value.knownUnsupportedBlocks.length === acceptedWarnings.length && value.unknownBlocks.length === 0 &&
    (!document.title || value.title === document.title) };
}

async function boundedBody(response) {
  const chunks=[];
  let size=0;
  for await (const chunk of response.body) {
    size+=chunk.length;
    if (size>LIMIT) fail('snapshot_too_large');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

async function capture(config, output, env=process.env, fetcher=fetch, nativeOverride=null) {
  const base=configuration(config,env.AFFINE_BASE_URL || 'http://127.0.0.1:3010');
  let cookie=env.AFFINE_COOKIE;
  if (env.AFFINE_AUTH_FILE) {
    const info=fs.lstatSync(env.AFFINE_AUTH_FILE);
    if (!info.isFile() || (info.mode & 0o077) || info.size>65536) fail('invalid_auth_file');
    const session=JSON.parse(fs.readFileSync(env.AFFINE_AUTH_FILE,'utf8'));
    if (session.origin!==base || typeof session.cookie!=='string') fail('invalid_auth_file');
    cookie=session.cookie;
  }
  if (!env.AFFINE_TOKEN && !cookie) fail('affine_authentication_required');
  const headers={};
  if (env.AFFINE_TOKEN) headers.Authorization='Bearer '+env.AFFINE_TOKEN;
  if (cookie) headers.Cookie=cookie;
  const versionResponse=await fetcher(base+'/graphql', {method:'POST',redirect:'error',
    signal:AbortSignal.timeout(15000),headers:{...headers,'Content-Type':'application/json'},
    body:JSON.stringify({query:'query { serverConfig { version } }'})});
  if (!versionResponse.ok) fail('affine_version_unavailable');
  const version=JSON.parse((await boundedBody(versionResponse)).toString()).data?.serverConfig?.version;
  if (version!=='0.27.4') fail('affine_codec_version_mismatch');
  const nativeRequire=nativeOverride ? null : createRequire('/app/package.json');
  const native=nativeOverride || nativeRequire('/app/dist/server-native.x64.node');
  const Y=nativeOverride ? null : nativeRequire('yjs');
  const batch=path.join(path.resolve(output),crypto.randomUUID());
  fs.mkdirSync(batch,{recursive:true,mode:0o700});
  const manifest={version:1,affine_version:version,workspace:config.workspace,
    server:'https://affine.joaopaulo.me',capture_started_at:new Date().toISOString(),documents:[]};
  for (const document of config.documents) {
    const item={id:document.id,complete:false};
    try {
      const response=await fetcher(base+'/api/workspaces/'+config.workspace+'/docs/'+document.id,
        {headers,redirect:'error',signal:AbortSignal.timeout(30000)});
      if (!response.ok) fail('affine_http_'+response.status);
      if (!(response.headers.get('content-type')||'').includes('application/octet-stream')) fail('not_a_snapshot');
      const bytes=await boundedBody(response);
      const value=decoded(native,bytes,document,manifest.server+'/workspace/'+config.workspace,Y ? inspectLayout(bytes,Y) : null);
      const snapshot=document.id+'.bin', markdown=document.id+'.md';
      fs.writeFileSync(path.join(batch,snapshot),bytes,{flag:'wx',mode:0o600});
      fs.writeFileSync(path.join(batch,markdown),value.markdown,{flag:'wx',mode:0o600});
      Object.assign(item,{title:value.title,complete:value.complete,markdown,snapshot,
        snapshot_sha256:sha(bytes),markdown_sha256:sha(value.markdown),
        unsupported:value.knownUnsupportedBlocks,acceptedWarnings:value.acceptedWarnings,unknown:value.unknownBlocks});
    } catch (error) {
      // Never emit cookies, response bodies, URLs with tokens, or native exception details.
      item.error=/^(affine_http_\d+|not_a_snapshot|snapshot_too_large|invalid_decoder_output)$/.test(error.message)
        ? error.message : 'capture_incomplete';
    }
    manifest.documents.push(item);
  }
  manifest.capture_completed_at=new Date().toISOString();
  manifest.complete=manifest.documents.every(d=>d.complete);
  fs.writeFileSync(path.join(batch,'manifest.json'),JSON.stringify(manifest,null,2)+'\n',{flag:'wx',mode:0o600});
  return {status:manifest.complete?'captured':'incomplete',manifest:path.join(batch,'manifest.json'),
    documents:manifest.documents.map(d=>({id:d.id,complete:d.complete,error:d.error}))};
}

module.exports={configuration,decoded,capture,inspectLayout};
if (require.main===module) {
  process.umask(0o077);
  (async()=>{
    if (process.argv.length!==4) fail('usage_node_reader_allowlist_json_private_output_directory');
    const input=fs.readFileSync(process.argv[2]);
    if(input.length>65536) fail('allowlist_too_large');
    console.log(JSON.stringify(await capture(JSON.parse(input),process.argv[3])));
  })().catch(error=>{
    const safe=['invalid_origin','invalid_allowlist','invalid_auth_file','affine_authentication_required','affine_codec_version_mismatch',
      'affine_version_unavailable','allowlist_too_large','usage_node_reader_allowlist_json_private_output_directory'];
    console.log(JSON.stringify({status:'blocked',reason:safe.includes(error.message)?error.message:'reader_failed'}));
    process.exitCode=1;
  });
}
