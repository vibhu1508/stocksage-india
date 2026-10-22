"""
Minimal client for NSE's official MCP servers (plan §5.10): JSON-RPC over streamable HTTP.

NSE blocks cloud servers on www.nseindia.com and nsearchives (403 from Render); these MCP
servers answer them. The NSE MCP adapter builds on this client.
"""

import json
from typing import Any, Optional

import httpx

SERVERS = {
    "bhavcopy": "https://mcp.nseindia.in/bhavcopy/cm/mcp",  # end-of-day history, movers, breadth, search
    "cmmkt": "https://mcp.nseindia.in/cmmkt/mcp",  # intraday snapshots, crawled about every 5 minutes
}
PROTOCOL_VERSION = "2025-03-26"
_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


class McpError(RuntimeError):
    """The MCP server returned an error or a response we could not read."""


def _read(resp: httpx.Response) -> dict:
    """A JSON-RPC reply, sent either as plain JSON or as server-sent events."""
    resp.raise_for_status()
    if "text/event-stream" in resp.headers.get("content-type", ""):
        events = [line[5:].strip() for line in resp.text.splitlines() if line.startswith("data:")]
        if not events:
            raise McpError("empty event stream")
        return json.loads(events[-1])
    return resp.json()


class McpSession:
    """One MCP session: initialize once, then list or call tools."""

    def __init__(self, url: str, client: httpx.AsyncClient):
        self.url = url
        self.client = client
        self.session_id: Optional[str] = None
        self._next_id = 0

    async def _post(self, payload: dict) -> httpx.Response:
        headers = {**_HEADERS, **({"Mcp-Session-Id": self.session_id} if self.session_id else {})}
        return await self.client.post(self.url, headers=headers, json=payload)

    async def _rpc(self, method: str, params: Optional[dict] = None) -> dict:
        self._next_id += 1
        reply = _read(await self._post({"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params or {}}))
        if reply.get("error"):
            raise McpError(f"{method}: {reply['error']}")
        return reply.get("result") or {}

    async def initialize(self) -> dict:
        self._next_id += 1
        resp = await self._post({
            "jsonrpc": "2.0", "id": self._next_id, "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                       "clientInfo": {"name": "stocksage-india", "version": "1.0"}},
        })
        reply = _read(resp)
        if reply.get("error"):
            raise McpError(f"initialize: {reply['error']}")
        self.session_id = resp.headers.get("mcp-session-id")
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return reply.get("result") or {}

    async def list_tools(self) -> list[dict]:
        return (await self._rpc("tools/list")).get("tools", [])

    async def call_tool(self, name: str, arguments: Optional[dict] = None) -> Any:
        """Tool output, decoded from JSON when the tool returns JSON text."""
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        text = "".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        if result.get("isError"):
            raise McpError(f"{name}: {text[:200]}")
        try:
            return json.loads(text)
        except ValueError:
            return text
