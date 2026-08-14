import asyncio
import os
import sys

sys.path.insert(0, r"D:\UPeU\mcp-cerebro")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=[r"D:\UPeU\mcp-cerebro\run_server.py"],
        env={
            **os.environ,
            "CEREBRO_VAULT_PATH": r"D:\UPeU\Cerebro universitario",
            "CEREBRO_TEMP_DIR": r"D:\UPeU\mcp-cerebro\temporal",
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("HERRAMIENTAS:", [t.name for t in tools.tools])

            res = await session.call_tool("transcribir_audio", {})
            print("TRANSCRIBIR:", res.content[0].text[:200])
            print("PRUEBA_VENV_OK")


asyncio.run(main())