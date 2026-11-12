const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {configuration,decoded,capture,inspectLayout}=require('./knowledge-affine-reader.cjs');
const allowlist={workspace:'workspace',documents:[{id:'doc',title:'Original'}]};
const value={title:'Original',markdown:'Açúcar and [[links]].',knownUnsupportedBlocks:[],unknownBlocks:[]};
const native={parseDocToMarkdown:()=>({...value})};

test('only known origins, bounded document allowlists and safe IDs',()=>{
  assert.equal(configuration(allowlist,'https://affine.joaopaulo.me/'),'https://affine.joaopaulo.me');
  for(const url of ['https://evil.test','https://u:p@affine.joaopaulo.me','https://affine.joaopaulo.me/?secret=x'])
    assert.throws(()=>configuration(allowlist,url));
  assert.throws(()=>configuration({workspace:'x',documents:[{id:'../escape'}]},'http://127.0.0.1:3010'));
  assert.throws(()=>configuration({...allowlist,documents:[]},'http://127.0.0.1:3010'));
});

test('unsupported, unknown or mismatched titles are incomplete',()=>{
  assert.equal(decoded(native,Buffer.from('x'),allowlist.documents[0],'prefix').complete,true);
  for(const change of [{unknownBlocks:['future:block']},{knownUnsupportedBlocks:['affine:surface']},{title:'Wrong'}]) {
    const decoder={parseDocToMarkdown:()=>({...value,...change})};
    assert.equal(decoded(decoder,Buffer.from('x'),allowlist.documents[0],'prefix').complete,false);
  }
});

test('only explicitly qualified note wrappers can be accepted; warnings are retained',()=>{
  const decoder={parseDocToMarkdown:()=>({...value,knownUnsupportedBlocks:['block:doc:note:affine:note']})};
  assert.equal(decoded(decoder,Buffer.from('x'),{id:'doc'},'prefix').complete,false);
  const result=decoded(decoder,Buffer.from('x'),{id:'doc',acceptNoteContainer:true},'prefix');
  assert.equal(result.complete,true);
  assert.deepEqual(result.acceptedWarnings,['block:doc:note:affine:note']);
  decoder.parseDocToMarkdown=()=>({...value,knownUnsupportedBlocks:['block:doc:surface:affine:surface']});
  assert.equal(decoded(decoder,Buffer.from('x'),{id:'doc',acceptNoteContainer:true},'prefix').complete,false);
});

test('a surface warning requires explicit permission AND an independently empty canvas',()=>{
  const decoder={parseDocToMarkdown:()=>({...value,knownUnsupportedBlocks:['canvas:affine:surface']})};
  const document={id:'doc',acceptEmptySurface:true};
  assert.equal(decoded(decoder,Buffer.from('x'),document,'prefix').complete,false);
  assert.equal(decoded(decoder,Buffer.from('x'),document,'prefix',{notes:new Set(),emptySurfaces:new Set()}).complete,false);
  assert.equal(decoded(decoder,Buffer.from('x'),document,'prefix',{notes:new Set(),emptySurfaces:new Set(['canvas'])}).complete,true);
});

test('qualified imported note wrappers match the complete Yjs block ID',()=>{
  const decoder={parseDocToMarkdown:()=>({...value,knownUnsupportedBlocks:['block:doc:note:affine:note']})};
  const document={id:'doc',acceptNoteContainer:true};
  const layout={notes:new Set(['block:doc:note']),emptySurfaces:new Set()};
  assert.equal(decoded(decoder,Buffer.from('x'),document,'prefix',layout).complete,true);
  for (const id of ['note','block:other:note']) {
    assert.equal(decoded(decoder,Buffer.from('x'),document,'prefix',{...layout,notes:new Set([id])}).complete,false);
  }
  assert.equal(decoded(decoder,Buffer.from('x'),{id:'doc'},'prefix',layout).complete,false);
});

test('colon-containing canvas IDs must match the independently empty surface exactly',()=>{
  const decoder={parseDocToMarkdown:()=>({...value,knownUnsupportedBlocks:['block:doc:canvas:affine:surface']})};
  const document={id:'doc',acceptEmptySurface:true};
  const layout={notes:new Set(),emptySurfaces:new Set(['block:doc:canvas'])};
  assert.equal(decoded(decoder,Buffer.from('x'),document,'prefix',layout).complete,true);
  for (const id of ['canvas','block:other:canvas']) {
    assert.equal(decoded(decoder,Buffer.from('x'),document,'prefix',{...layout,emptySurfaces:new Set([id])}).complete,false);
  }
});

test('real Yjs snapshots distinguish qualified wrappers, empty canvases, and nonempty canvases',
  {skip:process.env.AFFINE_READER_REAL_YJS!=='1'},()=>{
    const Y=require('node:module').createRequire('/app/package.json')('yjs');
    const doc=new Y.Doc();
    const blocks=doc.getMap('blocks');
    const note=new Y.Map();
    note.set('sys:flavour','affine:note');
    blocks.set('block:doc:note',note);
    const surface=new Y.Map();
    surface.set('sys:flavour','affine:surface');
    surface.set('sys:children',new Y.Array());
    const elements=new Y.Map();
    surface.set('prop:elements',elements);
    blocks.set('block:doc:surface',surface);
    const document={id:'doc',acceptNoteContainer:true,acceptEmptySurface:true};
    const decoder={parseDocToMarkdown:()=>({...value,knownUnsupportedBlocks:[
      'block:doc:note:affine:note','block:doc:surface:affine:surface']})};
    function result() {
      const bytes=Y.encodeStateAsUpdate(doc);
      return decoded(decoder,bytes,document,'prefix',inspectLayout(bytes,Y));
    }
    try {
      assert.equal(result().complete,true);
      elements.set('shape',{type:'rect'});
      assert.equal(result().complete,false);
      elements.delete('shape');
      assert.equal(result().complete,true);
      decoder.parseDocToMarkdown=()=>({...value,unknownBlocks:['future:block']});
      assert.equal(result().complete,false);
    } finally { doc.destroy(); }
  });

test('missing authentication makes no request',async()=>{
  await assert.rejects(capture(allowlist,'/tmp/unused',{},()=>assert.fail('network'),native),/authentication_required/);
});

test('private auth file is bound to the configured origin',async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'affine-auth-'));
  const auth=path.join(root,'session.json');
  try {
    fs.writeFileSync(auth,JSON.stringify({origin:'https://affine.joaopaulo.me',cookie:'session=private'}),{mode:0o600});
    await assert.rejects(capture(allowlist,root,{AFFINE_AUTH_FILE:auth},()=>assert.fail('network'),native),/invalid_auth_file/);
  } finally { fs.rmSync(root,{recursive:true}); }
});

test('readable-by-others credentials are rejected before network access',async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'affine-auth-'));
  const auth=path.join(root,'session.json');
  try {
    fs.writeFileSync(auth,JSON.stringify({origin:'http://127.0.0.1:3010',cookie:'session=private'}),{mode:0o600});
    fs.chmodSync(auth,0o644);
    await assert.rejects(capture(allowlist,root,{AFFINE_AUTH_FILE:auth},()=>assert.fail('network'),native),/invalid_auth_file/);
  } finally { fs.rmSync(root,{recursive:true}); }
});

test('version drift is rejected before decoding',async()=>{
  await assert.rejects(capture(allowlist,'/tmp/unused',{AFFINE_TOKEN:'secret'},async()=>
    new Response(JSON.stringify({data:{serverConfig:{version:'0.28.0'}}})),native),/codec_version_mismatch/);
});

test('private capture stores both original snapshot and Markdown',async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'affine-reader-'));
  const calls=[];
  try {
    const fetcher=async(url,options)=>{
      calls.push({url,options});
      return url.endsWith('/graphql')?new Response(JSON.stringify({data:{serverConfig:{version:'0.27.4'}}})):
        new Response('snapshot',{headers:{'Content-Type':'application/octet-stream'}});
    };
    const result=await capture(allowlist,root,{AFFINE_TOKEN:'secret'},fetcher,native);
    const manifest=JSON.parse(fs.readFileSync(result.manifest));
    assert.equal(manifest.complete,true);
    assert.equal(fs.readFileSync(path.join(path.dirname(result.manifest),'doc.md'),'utf8'),value.markdown);
    assert.equal(fs.statSync(result.manifest).mode&0o777,0o600);
    assert.equal(calls[1].options.redirect,'error');
    assert.equal(calls[1].options.headers.Authorization,'Bearer secret');
    assert.equal(JSON.stringify(manifest).includes('secret'),false);
  } finally { fs.rmSync(root,{recursive:true}); }
});

test('403 capture is incomplete, never a source deletion or raw error',async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'affine-reader-'));
  try {
    const result=await capture(allowlist,root,{AFFINE_TOKEN:'secret'},async url=>
      url.endsWith('/graphql')?new Response(JSON.stringify({data:{serverConfig:{version:'0.27.4'}}})):
        new Response('private upstream secret',{status:403}),native);
    assert.equal(result.status,'incomplete');
    assert.equal(result.documents[0].error,'affine_http_403');
    assert.equal(JSON.stringify(result).includes('private upstream'),false);
  } finally { fs.rmSync(root,{recursive:true}); }
});
