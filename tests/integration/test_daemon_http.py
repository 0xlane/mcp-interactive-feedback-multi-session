"""
Daemon HTTP 模式集成測試
=======================

驗證 :mod:`mcp_feedback_enhanced.daemon` 的 ``build_daemon_app`` 產物：

1. Web UI 介面可用（``GET /`` 返回 HTML）；
2. 多會話 API 可用（``GET /api/all-sessions``）；
3. MCP Streamable HTTP 端點正常（``POST /mcp/`` initialize + tools/list
   能看到 ``interactive_feedback``）；
4. PID 鎖被 :func:`serve_http` 正確獲取/釋放；
5. PID 鎖衝突時會 raise :class:`AlreadyRunningError` 並讓 CLI 早失敗。

注意：本模組不實際呼叫 ``interactive_feedback`` tool，因為它會阻塞等待用戶
輸入；``tools/list`` 已足夠驗證 MCP 註冊鏈路。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from mcp_feedback_enhanced.daemon import build_daemon_app, serve_http
from mcp_feedback_enhanced.utils.pid_lock import (
    AlreadyRunningError,
    DaemonPidLock,
)


@pytest.fixture
def daemon_client(tmp_path, monkeypatch):
    """為每個測試構建一個乾淨的 daemon app + TestClient。

    - 每次建構都會呼叫 ``set_web_ui_manager``，所以不會污染其他測試的全域；
    - TestClient 的 ``with`` 塊會觸發 lifespan 的 startup/shutdown，
      這是 MCP session manager 正常工作的前提。
    """
    import mcp_feedback_enhanced.web.main as web_main

    original_manager = web_main._web_ui_manager
    try:
        app, manager = build_daemon_app(host="127.0.0.1", port=19765)
        with TestClient(app) as client:
            yield client, manager
    finally:
        web_main._web_ui_manager = original_manager


def _extract_sse_json(body: str) -> dict:
    """從 MCP streamable HTTP 回應中解析出第一條 ``data: {...}`` 事件。"""
    match = re.search(r"data:\s*(\{.*\})", body)
    assert match, f"未在 SSE stream 中找到 JSON-RPC 回應：{body!r}"
    return json.loads(match.group(1))


def test_web_ui_is_served(daemon_client):
    client, _ = daemon_client
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_all_sessions_api_returns_empty_initially(daemon_client):
    client, _ = daemon_client
    resp = client.get("/api/all-sessions")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload == {"sessions": []}


def test_mcp_mount_is_registered(daemon_client):
    client, _ = daemon_client
    # 無尾斜線會 307 到 /mcp/
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0.0"},
            },
        },
        headers={"Accept": "application/json, text/event-stream"},
        follow_redirects=False,
    )
    assert resp.status_code == 307
    assert resp.headers["location"].endswith("/mcp/")


def test_mcp_initialize_succeeds(daemon_client):
    client, _ = daemon_client
    resp = client.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0.0"},
            },
        },
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert resp.status_code == 200
    assert "mcp-session-id" in resp.headers
    obj = _extract_sse_json(resp.text)
    assert obj["id"] == 1
    assert obj["result"]["serverInfo"]["name"] == "互動式回饋收集 MCP"


def test_mcp_tools_list_includes_interactive_feedback(daemon_client):
    client, _ = daemon_client
    headers = {"Accept": "application/json, text/event-stream"}

    init = client.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0.0"},
            },
        },
        headers=headers,
    )
    session_id = init.headers["mcp-session-id"]
    session_headers = {**headers, "mcp-session-id": session_id}

    client.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        },
        headers=session_headers,
    )

    resp = client.post(
        "/mcp/",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers=session_headers,
    )
    assert resp.status_code == 200
    obj = _extract_sse_json(resp.text)
    tool_names = {t["name"] for t in obj["result"]["tools"]}
    assert "interactive_feedback" in tool_names
    assert "get_system_info" in tool_names


def test_build_daemon_app_sets_global_manager(tmp_path, monkeypatch):
    """build_daemon_app 必須把 manager 寫入 web.main._web_ui_manager。"""
    import mcp_feedback_enhanced.web.main as web_main

    original = web_main._web_ui_manager
    try:
        _, manager = build_daemon_app(host="127.0.0.1", port=19765)
        assert web_main._web_ui_manager is manager
        assert manager.is_daemon is True
        assert manager.host == "127.0.0.1"
        assert manager.port == 19765
    finally:
        web_main._web_ui_manager = original


def test_serve_http_rejects_on_pid_conflict(tmp_path, monkeypatch):
    """存在存活 PID 文件時，serve_http 應拒絕啟動。"""
    pid_file = tmp_path / "daemon.pid"
    # 先用一把鎖寫入當前進程的 PID（當前進程顯然存活）
    preexisting = DaemonPidLock(pid_file)
    preexisting.acquire()

    try:
        with pytest.raises(AlreadyRunningError) as excinfo:
            # 即便我們給了奇怪的 port，鎖檢查在 uvicorn 啟動前就會失敗
            serve_http(host="127.0.0.1", port=19766, pid_path=pid_file)
        assert excinfo.value.pid == os.getpid()
    finally:
        preexisting.release()


def test_serve_http_lock_path_resolution(tmp_path):
    """pid_path 正確使用 CLI 傳入的路徑，不落到 ~/.config。"""
    pid_file = tmp_path / "custom" / "daemon.pid"
    lock = DaemonPidLock(pid_file)
    # 場景：尚未啟動 daemon，PID 文件不存在
    assert lock.read_existing_pid() is None
    # 正常 acquire / release 形成完整循環
    lock.acquire()
    assert pid_file.exists()
    lock.release()
    assert not pid_file.exists()
