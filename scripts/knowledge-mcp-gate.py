#!/usr/bin/env python3
"""Qualify official Hindsight MCP restrictions in a disposable synthetic bank.

Run inside the Hindsight image (which already includes the official MCP client).
No production bank is written. Authentication comes from HINDSIGHT_API_KEY.
"""
import asyncio
import json
import os
import urllib.request
import uuid


async def qualify():
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    bank = 'knowledge-gate-mcp-' + uuid.uuid4().hex[:12]
    base = 'http://127.0.0.1:8888'
    api = base + '/v1/default/banks/' + bank
    headers = {'Content-Type':'application/json'}
    if os.environ.get('HINDSIGHT_API_KEY'):
        headers['Authorization'] = 'Bearer ' + os.environ['HINDSIGHT_API_KEY']
    def request(method, path, data):
        req = urllib.request.Request(api+path,json.dumps(data).encode(),headers,method=method)
        with urllib.request.urlopen(req,timeout=15) as response:
            return json.load(response)
    request('PUT','',{})
    allowed = ['recall','reflect','get_document','list_documents','list_memories','get_memory']
    request('PATCH','/config',{'updates':{'mcp_enabled_tools':allowed}})
    checks = {}
    async with streamablehttp_client(base+'/mcp/'+bank+'/',headers=headers) as (read,write,_):
        async with ClientSession(read,write) as session:
            await session.initialize()
            result=await session.list_tools()
            names={tool.name for tool in result.tools}
            checks['allowlist_enforced_in_discovery']=names==set(allowed)
            denied=await session.call_tool('retain',{'content':'Synthetic restriction probe.',
                'document_id':'mcp-denied-probe'})
            checks['retain_invocation_denied']=bool(denied.isError)
            denied=await session.call_tool('update_bank',{'mission':'Synthetic denied change.'})
            checks['bank_update_invocation_denied']=bool(denied.isError)
            readback=await session.call_tool('list_documents',{})
            checks['permitted_read_succeeds']=not readback.isError
    return {'gate':'official-hindsight-mcp','bank':bank,'status':'passed' if all(checks.values()) else 'failed',
        'checks':checks,'remote_authentication_qualified':False,
        'remaining':'Keep loopback access. Qualify authenticated remote access before client rollout.'}


if __name__=='__main__':
    try:
        print(json.dumps(asyncio.run(qualify()),sort_keys=True))
    except Exception:
        print(json.dumps({'gate':'official-hindsight-mcp','status':'blocked','reason':'mcp_probe_failed'}))
        raise SystemExit(1)
