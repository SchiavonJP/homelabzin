"""Read-only transport gate using the real MCP SDK. Run inside Xereta."""
import asyncio,json,os
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from app.config import Settings

async def main():
    cfg=Settings()
    headers={'Authorization':'Bearer '+cfg.agent_read_token.get_secret_value()}
    async with streamablehttp_client(os.environ.get('XERETA_MCP_GATE_URL','http://127.0.0.1:3101/mcp/'),headers=headers) as (read,write,_):
        async with ClientSession(read,write) as session:
            await session.initialize()
            names={x.name for x in (await session.list_tools()).tools}
            listed=await session.call_tool('list_notes',{})
            status=await session.call_tool('xereta_status',{})
            denied=await session.call_tool('xereta_request_run',{'idempotency_key':'gate-reader-must-not-run'})
            note_write=await session.call_tool('write_note',{'path':'Homelab/Comandos.md','content':'denied probe'})
            checks={'tools_listed':{'xereta_status','xereta_request_run','xereta_answer_question','list_notes','read_note','search_notes','write_note','get_backlinks','list_skills','get_skill','search_skills','get_user_model','get_memory','search_memory','get_recent_synthesis'}.issubset(names),'list_notes':not listed.isError,
                    'status':not status.isError,'run_denied':bool(denied.isError),'write_denied':bool(note_write.isError)}
            print(json.dumps({'gate':'xereta-mcp-streamable','passed':all(checks.values()),'tools':sorted(names),'checks':checks}))
            if not all(checks.values()):raise SystemExit(1)
asyncio.run(main())
