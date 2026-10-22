"""NSE MCP client against a fake server. Run: python -m tests.test_nse_mcp (from backend/), or pytest."""

import asyncio
import json

import httpx

from services.nse_mcp import McpError, McpSession

seen_sessions = []


def fake_server(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    seen_sessions.append(request.headers.get("mcp-session-id"))
    if body["method"] == "initialize":
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"serverInfo": {"name": "fake"}}},
                              headers={"mcp-session-id": "abc"})
    if body["method"] == "notifications/initialized":
        return httpx.Response(202)
    if body["method"] == "tools/list":  # answered as server-sent events, like NSE's servers
        payload = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [{"name": "cm_get_data_status"}]}})
        return httpx.Response(200, text=f"event: message\ndata: {payload}\n\n", headers={"content-type": "text/event-stream"})
    if body["params"]["name"] == "cm_get_data_status":
        text = json.dumps({"crawlIntervalMinutes": 5})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"content": [{"type": "text", "text": text}]}})
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"isError": True, "content": [{"type": "text", "text": "indexName is required"}]}})


def test_session_handshake_events_and_tool_results():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake_server)) as client:
            s = McpSession("https://example.test/mcp", client)
            assert (await s.initialize())["serverInfo"] == {"name": "fake"}
            assert [t["name"] for t in await s.list_tools()] == ["cm_get_data_status"]
            assert await s.call_tool("cm_get_data_status") == {"crawlIntervalMinutes": 5}
            try:
                await s.call_tool("cm_get_index_quote")
                raise AssertionError("tool error must raise")
            except McpError as exc:
                assert "indexName is required" in str(exc)

    asyncio.run(run())
    assert seen_sessions[0] is None and set(seen_sessions[1:]) == {"abc"}  # session id sent after initialize


if __name__ == "__main__":
    test_session_handshake_events_and_tool_results()
    print("ok test_session_handshake_events_and_tool_results")
