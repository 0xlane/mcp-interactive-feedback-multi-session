#!/usr/bin/env python3
"""Inject multi-round test session data into a running daemon via MCP HTTP + WebSocket."""

import asyncio
import json
import uuid
import aiohttp

BASE = "http://127.0.0.1:9999"
MCP_URL = f"{BASE}/mcp"
WS_URL = "ws://127.0.0.1:9999/ws?lang=zh-CN"

ROUNDS = [
    {
        "summary": "# Round 1\n\nCompleted project setup:\n- Installed deps\n- Configured linting",
        "user_feedback": "Looks good, now add TypeScript support.",
    },
    {
        "summary": "# Round 2\n\nAdded TypeScript support:\n- Installed typescript and ts-node\n- Created tsconfig.json",
        "user_feedback": "Nice, also add unit testing framework.",
    },
    {
        "summary": "# Round 3\n\nAdded testing framework:\n- Installed jest with ts-jest\n- Created jest.config.ts\n- Added sample test",
        "user_feedback": None,  # Last round: wait for user to submit manually
    },
]


class MCPClient:
    """Minimal MCP Streamable HTTP client."""

    def __init__(self):
        self._req_id = 0
        self._mcp_session_id = None

    def _next_id(self):
        self._req_id += 1
        return self._req_id

    async def _post(self, http: aiohttp.ClientSession, payload: dict) -> dict | None:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._mcp_session_id:
            headers["Mcp-Session-Id"] = self._mcp_session_id
        async with http.post(MCP_URL, json=payload, headers=headers) as resp:
            if sid := resp.headers.get("Mcp-Session-Id"):
                self._mcp_session_id = sid
            if resp.status == 202:
                return None
            if resp.status != 200:
                print(f"  [MCP] POST error {resp.status}: {await resp.text()}")
                return None
            ct = resp.headers.get("Content-Type", "")
            if "text/event-stream" in ct:
                return await self._parse_sse(resp)
            text = await resp.text()
            if text.strip():
                return json.loads(text)
            return None

    async def _parse_sse(self, resp) -> dict | None:
        """Parse SSE stream and return the last JSON-RPC message with a result/error."""
        last_result = None
        async for line_bytes in resp.content:
            line = line_bytes.decode("utf-8").rstrip("\r\n")
            if line.startswith("data: "):
                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                    if "result" in data or "error" in data:
                        last_result = data
                except json.JSONDecodeError:
                    pass
        return last_result

    async def initialize(self, http: aiohttp.ClientSession):
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test-injector", "version": "1.0.0"},
            },
        }
        result = await self._post(http, payload)
        if result and "result" in result:
            print(f"[MCP] Initialized. Session: {self._mcp_session_id}")
            # Send initialized notification
            await self._post(http, {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            })
            return True
        print(f"[MCP] Init failed: {result}")
        return False

    async def call_tool(self, http: aiohttp.ClientSession, name: str, arguments: dict) -> asyncio.Task:
        """Start a tool call and return immediately (tool may block server-side)."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._mcp_session_id:
            headers["Mcp-Session-Id"] = self._mcp_session_id

        async def do_call():
            async with http.post(MCP_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if sid := resp.headers.get("Mcp-Session-Id"):
                    self._mcp_session_id = sid
                ct = resp.headers.get("Content-Type", "")
                if "text/event-stream" in ct:
                    result = await self._parse_sse(resp)
                    return resp.status, json.dumps(result) if result else ""
                text = await resp.text()
                return resp.status, text

        return asyncio.create_task(do_call())


async def wait_for_session(http: aiohttp.ClientSession, title: str, timeout: float = 15.0) -> str | None:
    """Poll /api/all-sessions until a session with the given title appears in 'waiting' status."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        async with http.get(f"{BASE}/api/all-sessions?lang=zh-CN") as resp:
            if resp.status == 200:
                data = await resp.json()
                for s in data.get("sessions", []):
                    if s.get("title") == title and s.get("status") == "waiting":
                        return s["session_id"]
        await asyncio.sleep(0.5)
    return None


async def submit_feedback(session_id: str, feedback: str):
    """Connect to WS and submit feedback for a specific session."""
    async with aiohttp.ClientSession() as http:
        async with http.ws_connect(WS_URL) as ws:
            # Drain initial messages
            try:
                while True:
                    await asyncio.wait_for(ws.receive(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

            await ws.send_json({
                "type": "submit_feedback",
                "session_id": session_id,
                "feedback": feedback,
                "images": [],
            })

            # Wait for confirmation
            try:
                while True:
                    msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "session_updated":
                            info = data.get("session_info", {})
                            if info.get("session_id") == session_id:
                                return info.get("status")
            except asyncio.TimeoutError:
                pass
    return "unknown"


async def add_user_message(http: aiohttp.ClientSession, session_id: str, content: str):
    """POST a user message to the API."""
    async with http.post(f"{BASE}/api/add-user-message", json={
        "session_id": session_id,
        "content": content,
        "submission_method": "manual",
        "images": [],
    }) as resp:
        return resp.status == 200


async def main():
    title = "Test Multi-Round"
    project_dir = "/Users/reinject/local_project/mcp-interactive-feedback-multi-session"
    feedback_session_id = None

    async with aiohttp.ClientSession() as http:
        mcp = MCPClient()

        if not await mcp.initialize(http):
            print("[!] MCP initialization failed")
            return

        for i, round_data in enumerate(ROUNDS):
            print(f"\n=== Round {i + 1} / {len(ROUNDS)} ===")

            # Start the MCP tool call (it will block until feedback is submitted)
            args = {
                "project_directory": project_dir,
                "summary": round_data["summary"],
                "timeout": 600,
                "title": title,
            }
            if feedback_session_id:
                args["feedback_session_id"] = feedback_session_id

            print(f"  Calling interactive_feedback (title={title!r})...")
            tool_task = await mcp.call_tool(http, "interactive_feedback", args)

            # Wait for the session to appear in waiting status
            print("  Waiting for session to appear...")
            session_id = await wait_for_session(http, title, timeout=10.0)
            if not session_id:
                print("  [!] Session not found in time, trying to get result...")
                try:
                    status, text = await asyncio.wait_for(tool_task, timeout=5)
                    print(f"  Tool returned: status={status}")
                except asyncio.TimeoutError:
                    print("  [!] Tool call timed out")
                continue

            print(f"  Session found: {session_id}")
            feedback_session_id = session_id

            if round_data["user_feedback"] is None:
                print("  ⏳ Last round — waiting for you to submit feedback in the browser...")
                print(f"  Open http://127.0.0.1:9999 and submit feedback for session '{title}'")
                try:
                    status_code, text = await asyncio.wait_for(tool_task, timeout=300)
                    print(f"  Tool call completed: HTTP {status_code}")
                except asyncio.TimeoutError:
                    print("  Tool call timed out after 5 min")
                break

            # Small delay to simulate realistic timing
            await asyncio.sleep(1.5)

            # Submit feedback via WebSocket
            print(f"  Submitting feedback...")
            status = await submit_feedback(session_id, round_data["user_feedback"])
            print(f"  Feedback submitted, status: {status}")

            # Add user message via HTTP
            ok = await add_user_message(http, session_id, round_data["user_feedback"])
            print(f"  User message added: {ok}")

            # Wait for tool call to complete
            try:
                status_code, text = await asyncio.wait_for(tool_task, timeout=10)
                print(f"  Tool call completed: HTTP {status_code}")
                try:
                    result = json.loads(text)
                    if "result" in result:
                        content = result["result"].get("content", [])
                        for c in content:
                            if c.get("type") == "text" and "feedback_session_id" in c.get("text", ""):
                                pass
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                print("  Tool call still pending (will be picked up by next round)")

            await asyncio.sleep(2)

        # Final check
        print("\n=== Verification ===")
        async with http.get(f"{BASE}/api/all-sessions?lang=zh-CN") as resp:
            if resp.status == 200:
                data = await resp.json()
                for s in data.get("sessions", []):
                    if s.get("title") == title:
                        print(f"  Session ID: {s['session_id']}")
                        print(f"  Status: {s['status']}")
                        print(f"  AI summaries: {len(s.get('ai_summaries', []))}")
                        print(f"  User messages: {len(s.get('user_messages', []))}")
                        created = s.get("created_at", 0) / 1000
                        last_act = s.get("last_activity", 0) / 1000
                        print(f"  Duration (last_activity - created_at): {last_act - created:.1f}s")

    print("\n[OK] Done. Refresh the browser to see the session.")


if __name__ == "__main__":
    asyncio.run(main())
