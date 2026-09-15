from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from ..contracts import MCP_TOOL_NAMES

# TUN-09: the server and connector parity checker consume the same canonical
# catalog. The external connector may still require a deployment/schema refresh,
# which is verified separately after the runtime upgrade.
REQUIRED_TOOLS = set(MCP_TOOL_NAMES)



def _tool_payload(result: Any) -> Any:
    structured = getattr(result, "structured_content", None)
    if structured is None:
        structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
    return None


async def verify(url: str) -> dict[str, Any]:
    # MCP SDK v2 high-level client performs protocol negotiation automatically.
    from mcp.client.client import Client

    async with Client(url) as client:
        tools_result = await client.list_tools()
        names = sorted(t.name for t in tools_result.tools)
        missing = sorted(REQUIRED_TOOLS.difference(names))
        health_result = await client.call_tool("health", {})
        health = _tool_payload(health_result)
        server_info = getattr(client, "server_info", None)
        ok = (
            not missing
            and not bool(getattr(health_result, "is_error", False))
            and isinstance(health, dict)
            and health.get("service") in {"READY", "RESOURCE_BLOCKED"}
        )
        return {
            "status": "PASS" if ok else "FAIL",
            "url": url,
            "server": getattr(server_info, "name", None),
            "protocol_version": str(getattr(client, "protocol_version", "")),
            "tool_count": len(names),
            "tools": names,
            "missing_tools": missing,
            "health": health,
        }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    args = parser.parse_args(argv)
    result = asyncio.run(verify(args.url))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
