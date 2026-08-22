"""Demonstrate MCP discovery and invocation over STDIO.

Starts ``mcp_server.server`` as a subprocess, lists the tools it advertises,
and calls each one — which is exactly what a conforming client (Claude
Desktop, an agent runtime, a notebook) does. Run it to verify the server works
without wiring up a real client.

    python -m mcp_server.test_mcp_client
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def main() -> int:
    from fastmcp import Client

    print("Connecting to mcp_server.server over STDIO…\n")

    # The server is launched as a subprocess speaking MCP on stdin/stdout.
    from fastmcp.client.transports import PythonStdioTransport

    transport = PythonStdioTransport(
        script_path=str(ROOT / "mcp_server" / "server.py"),
        python_cmd=sys.executable,
    )

    async with Client(transport) as client:
        # --- discovery ---
        tools = await client.list_tools()
        print(f"Discovered {len(tools)} tools:")
        for tool in tools:
            first_line = (tool.description or "").strip().split("\n")[0]
            print(f"  - {tool.name}: {first_line}")
        print()

        expected = {"search_circulars", "get_obligations", "as_of_lookup"}
        missing = expected - {t.name for t in tools}
        if missing:
            print(f"MISSING TOOLS: {missing}")
            return 1

        # --- invocation: search ---
        print("Calling search_circulars('margin collection reporting timeline')…")
        result = await client.call_tool(
            "search_circulars",
            {"query": "margin collection reporting timeline", "top_k": 3},
        )
        payload = _payload(result)
        results = payload.get("results", [])
        print(f"  {len(results)} passage(s), refused={payload.get('refused')}")
        for item in results[:2]:
            print(f"    {item['circular_number']}  score={item['score']}")
        print()

        # --- invocation: obligations for the first hit ---
        if results:
            number = results[0]["circular_number"]
            print(f"Calling get_obligations({number!r})…")
            payload = _payload(
                await client.call_tool("get_obligations", {"circular_number": number})
            )
            obligations = payload.get("obligations", [])
            print(f"  {len(obligations)} obligation(s)")
            for item in obligations[:2]:
                print(f"    [{item['modality']}] {item['text'][:70]}…")
            print()

        # --- invocation: point in time ---
        print("Calling as_of_lookup(..., as_of='2021-06-30')…")
        payload = _payload(
            await client.call_tool(
                "as_of_lookup",
                {"question": "what were the KYC verification requirements", "as_of": "2021-06-30"},
            )
        )
        print(
            f"  {len(payload.get('results', []))} passage(s) in force; "
            f"{payload.get('excluded_by_temporal_filter', 0)} excluded as superseded"
        )
        print()

        # --- error handling: tools return readable errors, never raise ---
        print("Calling get_obligations with an unknown circular…")
        payload = _payload(
            await client.call_tool(
                "get_obligations", {"circular_number": "SEBI/HO/NOPE/CIR/P/1999/1"}
            )
        )
        print(f"  error: {payload.get('error')}")

    print("\nMCP discovery and invocation succeeded.")
    return 0


def _payload(result: object) -> dict:
    """Extract the JSON payload from a tool result across fastmcp versions."""
    data = getattr(result, "data", None)
    if isinstance(data, dict):
        return data
    content = getattr(result, "content", None) or result
    if isinstance(content, list) and content:
        text = getattr(content[0], "text", None)
        if text:
            return json.loads(text)
    if isinstance(content, dict):
        return content
    return {}


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(asyncio.run(main()))
