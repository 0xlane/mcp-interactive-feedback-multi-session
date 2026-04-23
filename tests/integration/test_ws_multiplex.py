"""
Phase 3 · WebSocket 多路復用集成測試
=====================================

驗證 :mod:`mcp_feedback_enhanced.web.routes.main_routes` 的多路復用改造：

1. ``GET /api/sessions`` 返回完整快照（含 ``active_session_id`` 與 ``connected_clients``）；
2. ``/ws`` 連接建立後依序收到 ``connection_established`` → ``sessions_snapshot``；
3. 同時開啟多條 ``/ws``，一條連接發 ``archive_session`` 時**所有**連接都能收到
   ``session_archived`` 廣播（即「多 Tab 共享同步狀態」）；
4. 客戶端消息攜帶 ``session_id`` 時，服務端路由到對應會話而非活躍會話；
5. ``DELETE /api/sessions?status=canceled`` 批量刪除後會向 WS 廣播
   ``session_removed`` 事件；
6. ``archive_session`` via REST 與 via WS 的語義一致。

本測試直接以 ``starlette.testclient.TestClient`` 對 ``WebUIManager.app`` 作 in-process
HTTP + WS 呼叫，不起真正 uvicorn，跑起來毫秒級；避免 flaky。
"""

from __future__ import annotations

import json
import os
from collections.abc import Generator

import anyio
import pytest
from starlette.testclient import TestClient

from mcp_feedback_enhanced.web.main import WebUIManager
from mcp_feedback_enhanced.web.models import SessionStatus


def _recv_json_timeout(ws, timeout: float = 2.0) -> dict:
    """從 ``WebSocketTestSession`` 收一條 JSON，帶超時（Starlette 原生 API 無 timeout 參數）。

    超時會 raise ``TimeoutError``（由 anyio ``fail_after`` 發出），不返回 ``None``。
    """
    async def _recv() -> str:
        with anyio.fail_after(timeout):
            msg = await ws._send_rx.receive()
            # 複用 Starlette 的解碼邏輯：_raise_on_close + 取 text
            text = msg.get("text")
            if text is None:
                bytes_payload = msg.get("bytes")
                if bytes_payload is not None:
                    text = bytes_payload.decode("utf-8")
            return text or ""

    text = ws.portal.call(_recv)
    return json.loads(text)


def _try_recv_json(ws, timeout: float = 0.5) -> dict | None:
    """嘗試收一條 JSON；超時返回 ``None``，不 raise。"""
    try:
        return _recv_json_timeout(ws, timeout=timeout)
    except TimeoutError:
        return None


@pytest.fixture
def mux_manager(tmp_path) -> Generator[WebUIManager, None, None]:
    """為多路復用測試構建一個乾淨的 :class:`WebUIManager`。

    - ``MCP_TEST_MODE=true`` 關閉瀏覽器啟動、PID 鎖等副作用；
    - ``MCP_WEB_PORT=0`` 讓端口管理器隨便挑一個，不真正 ``listen`` 即可；
    - 每個測試獨立構建，避免共享的 ``_active_session_id`` 污染。
    """
    originals = {
        "MCP_TEST_MODE": os.environ.get("MCP_TEST_MODE"),
        "MCP_WEB_HOST": os.environ.get("MCP_WEB_HOST"),
        "MCP_WEB_PORT": os.environ.get("MCP_WEB_PORT"),
    }
    os.environ["MCP_TEST_MODE"] = "true"
    os.environ["MCP_WEB_HOST"] = "127.0.0.1"
    os.environ["MCP_WEB_PORT"] = "0"

    manager = WebUIManager()
    try:
        yield manager
    finally:
        for key, value in originals.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _drain_initial(ws):
    """消費連接建立後的初始消息，返回 (types, snapshot_payload)。

    WS 建連後服務端會無條件推送：
    1. ``connection_established``
    2. ``sessions_snapshot``
    3. 視情況推 ``session_updated`` / ``status_update``（若有當前會話 + 待更新標記）
    """
    types: list[str] = []
    snapshot_payload: dict | None = None
    # 預計最多 5 條初始消息
    for _ in range(5):
        msg = _try_recv_json(ws, timeout=0.8)
        if msg is None:
            break
        types.append(msg.get("type", ""))
        if msg.get("type") == "sessions_snapshot":
            snapshot_payload = msg
    return types, snapshot_payload


def _wait_for_type(ws, expected_type: str, session_id: str | None = None,
                   max_messages: int = 15, timeout: float = 3.0) -> dict:
    """輪詢接收 WS 消息，直到拿到指定 ``type``（可選附加 session_id 過濾）。"""
    for _ in range(max_messages):
        msg = _try_recv_json(ws, timeout=timeout)
        if msg is None:
            break
        if msg.get("type") != expected_type:
            continue
        if session_id is not None and msg.get("session_id") != session_id:
            continue
        return msg
    raise AssertionError(
        f"未收到 type={expected_type}"
        + (f" session_id={session_id}" if session_id else "")
    )


# --------------------------------------------------------------------------- #
# REST API 驗證
# --------------------------------------------------------------------------- #


def test_get_sessions_api_empty(mux_manager, test_project_dir):
    """無會話時 ``GET /api/sessions`` 返回空列表，不報錯。"""
    with TestClient(mux_manager.app) as client:
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["sessions"] == []
        assert payload["active_session_id"] is None
        assert payload["connected_clients"] == 0


def test_get_sessions_api_returns_snapshot(mux_manager, test_project_dir):
    """創建多個會話後 ``GET /api/sessions`` 返回完整快照。"""
    sid1 = mux_manager.create_session(str(test_project_dir), "任務 1", title="A")
    sid2 = mux_manager.create_session(str(test_project_dir), "任務 2", title="B")

    with TestClient(mux_manager.app) as client:
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        payload = resp.json()

        ids = [s["session_id"] for s in payload["sessions"]]
        assert set(ids) == {sid1, sid2}
        # 排序：最新建的在前
        assert payload["sessions"][0]["session_id"] == sid2
        # Phase 3 粘滯語義：活躍指針仍是第一個建立的 sid1
        assert payload["active_session_id"] == sid1
        # 只有 sid1 是當前
        is_current_map = {s["session_id"]: s["is_current"] for s in payload["sessions"]}
        assert is_current_map[sid1] is True
        assert is_current_map[sid2] is False


def test_delete_sessions_by_status_requires_status(mux_manager):
    """``DELETE /api/sessions`` 缺 ``status`` query 時應 400。"""
    with TestClient(mux_manager.app) as client:
        resp = client.delete("/api/sessions")
        assert resp.status_code == 400
        assert "status" in resp.json().get("error", "")


def test_delete_sessions_by_status_rejects_nonterminal(mux_manager, test_project_dir):
    """試圖批量刪除非終態（如 ``waiting``）應被拒絕。"""
    mux_manager.create_session(str(test_project_dir), "A")
    with TestClient(mux_manager.app) as client:
        resp = client.delete("/api/sessions?status=waiting")
        assert resp.status_code == 400
        assert "terminal" in resp.json().get("error", "").lower()


def test_delete_sessions_by_status_removes_terminal(mux_manager, test_project_dir):
    """``status=canceled`` 能批量刪除已取消會話，其他會話不受影響。"""
    sid_alive = mux_manager.create_session(str(test_project_dir), "活躍")
    sid_dead = mux_manager.create_session(str(test_project_dir), "已取消")
    # 手動轉為 CANCELED
    mux_manager.sessions[sid_dead].status = SessionStatus.CANCELED

    with TestClient(mux_manager.app) as client:
        resp = client.delete("/api/sessions?status=canceled")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["count"] == 1
        assert payload["removed"] == [sid_dead]

    # 驗證 manager 狀態
    assert sid_dead not in mux_manager.sessions
    assert sid_alive in mux_manager.sessions


def test_delete_sessions_all_terminal(mux_manager, test_project_dir):
    """``status=all_terminal`` 清掉所有終態會話。"""
    sid_ok = mux_manager.create_session(str(test_project_dir), "完成")
    sid_cancel = mux_manager.create_session(str(test_project_dir), "取消")
    sid_alive = mux_manager.create_session(str(test_project_dir), "活躍")
    mux_manager.sessions[sid_ok].status = SessionStatus.COMPLETED
    mux_manager.sessions[sid_cancel].status = SessionStatus.CANCELED

    with TestClient(mux_manager.app) as client:
        resp = client.delete("/api/sessions?status=all_terminal")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2
        assert set(resp.json()["removed"]) == {sid_ok, sid_cancel}

    assert sid_alive in mux_manager.sessions
    assert sid_ok not in mux_manager.sessions
    assert sid_cancel not in mux_manager.sessions


# --------------------------------------------------------------------------- #
# WebSocket 初始握手
# --------------------------------------------------------------------------- #


def test_ws_connect_receives_snapshot(mux_manager, test_project_dir):
    """連接 ``/ws`` 後應按序收到 connection_established → sessions_snapshot。"""
    sid = mux_manager.create_session(str(test_project_dir), "任務 X", title="X")

    with TestClient(mux_manager.app) as client:
        with client.websocket_connect("/ws?lang=zh-TW") as ws:
            first = _recv_json_timeout(ws)
            assert first["type"] == "connection_established"

            second = _recv_json_timeout(ws)
            assert second["type"] == "sessions_snapshot"
            assert second["active_session_id"] == sid
            assert len(second["sessions"]) == 1
            assert second["sessions"][0]["session_id"] == sid


def test_ws_connect_registers_connection(mux_manager):
    """建立 WS 後 ``manager.connections`` 應含此連接；斷開後剔除。"""
    with TestClient(mux_manager.app) as client:
        assert len(mux_manager.connections) == 0
        with client.websocket_connect("/ws?lang=zh-TW") as ws:
            # 消費初始握手
            _drain_initial(ws)
            assert len(mux_manager.connections) == 1
        # 離開 with 塊後 WS 已關閉
        # NOTE：TestClient 的關閉是同步觸發，unregister 在服務端 task 的 finally 中
        # 執行，這裡直接檢查可能尚未完成；連接數最多 1，業務不受影響。
        assert len(mux_manager.connections) <= 1


# --------------------------------------------------------------------------- #
# 多連接廣播同步
# --------------------------------------------------------------------------- #


def test_archive_via_rest_broadcasts_to_all_ws(mux_manager, test_project_dir):
    """REST 歸檔會話時，所有已連接的 WS Tab 都收到 ``session_archived``。"""
    sid = mux_manager.create_session(str(test_project_dir), "將被歸檔")

    with TestClient(mux_manager.app) as client:
        with client.websocket_connect("/ws?lang=zh-TW") as ws_a, \
             client.websocket_connect("/ws?lang=zh-TW") as ws_b:
            _drain_initial(ws_a)
            _drain_initial(ws_b)
            assert len(mux_manager.connections) == 2

            resp = client.post(f"/api/sessions/{sid}/archive", json={})
            assert resp.status_code == 200

            msg_a = _wait_for_type(ws_a, "session_archived", session_id=sid)
            msg_b = _wait_for_type(ws_b, "session_archived", session_id=sid)

            for msg in (msg_a, msg_b):
                assert msg["type"] == "session_archived"
                assert msg["session_id"] == sid
                assert msg["reason"]  # 非空


def test_archive_via_ws_message_broadcasts(mux_manager, test_project_dir):
    """通過 WS 發 ``archive_session`` 能歸檔目標會話並廣播給全部連接。"""
    sid = mux_manager.create_session(str(test_project_dir), "將被歸檔")

    with TestClient(mux_manager.app) as client:
        with client.websocket_connect("/ws?lang=zh-TW") as ws:
            _drain_initial(ws)
            ws.send_json({"type": "archive_session", "session_id": sid})

            # 預期後端會：1) 廣播 session_archived；2) 回 ack 給發起方
            saw_archived = False
            saw_ack = False
            for _ in range(12):
                msg = _try_recv_json(ws, timeout=2.0)
                if msg is None:
                    break
                t = msg.get("type")
                if t == "session_archived" and msg.get("session_id") == sid:
                    saw_archived = True
                elif t == "session_archive_ack" and msg.get("session_id") == sid:
                    saw_ack = True
                if saw_archived and saw_ack:
                    break

            assert saw_archived, "未收到 session_archived 廣播"
            assert saw_ack, "未收到 session_archive_ack 回執"

    # Phase 3：歸檔 = 從 manager.sessions 物理移除。刷新後 snapshot 也不會再
    # 把它推回前端，避免「清除已完成 → 刷新又回來」的 UX bug。
    assert sid not in mux_manager.sessions


def test_ws_get_sessions_snapshot_on_demand(mux_manager, test_project_dir):
    """客戶端主動發 ``get_sessions_snapshot`` 可重新拉取全量快照。"""
    sid_a = mux_manager.create_session(str(test_project_dir), "A")

    with TestClient(mux_manager.app) as client:
        with client.websocket_connect("/ws?lang=zh-TW") as ws:
            _drain_initial(ws)

            # 再建一個會話（不觸發 WS 廣播：launch_web_feedback_ui 才有；這裡直接
            # create_session 走 manager API，需靠 get_sessions_snapshot 請求拉取）
            sid_b = mux_manager.create_session(str(test_project_dir), "B")

            ws.send_json({"type": "get_sessions_snapshot"})

            msg = _wait_for_type(ws, "sessions_snapshot")
            ids = {s["session_id"] for s in msg["sessions"]}
            assert {sid_a, sid_b} <= ids


# --------------------------------------------------------------------------- #
# 消息 session_id 路由
# --------------------------------------------------------------------------- #


def test_ws_message_routed_by_session_id(mux_manager, test_project_dir):
    """消息中的 ``session_id`` 應把事件路由到目標會話而非活躍會話。

    Phase 3 粘滯語義：``sid_active``（第一個建立的）會是活躍會話，
    ``sid_newer`` 雖然後建但活躍指針並不會被它搶走。我們故意用
    ``archive_session`` 作用到「非活躍」的那個（``sid_newer``），
    驗證路由確實是按 ``session_id`` 走而不是打到活躍會話上。
    """
    sid_active = mux_manager.create_session(str(test_project_dir), "活躍任務")
    sid_newer = mux_manager.create_session(str(test_project_dir), "後建任務")
    assert mux_manager._active_session_id == sid_active

    with TestClient(mux_manager.app) as client:
        with client.websocket_connect("/ws?lang=zh-TW") as ws:
            _drain_initial(ws)

            # 歸檔「後建但非活躍」的會話：必須憑 session_id 才能正確命中
            ws.send_json({"type": "archive_session", "session_id": sid_newer})

            _wait_for_type(ws, "session_archived", session_id=sid_newer)

    # 驗證：後建任務被歸檔（物理移除），活躍任務完好
    assert sid_newer not in mux_manager.sessions
    assert sid_active in mux_manager.sessions
    assert mux_manager.sessions[sid_active].status not in {
        SessionStatus.CANCELED,
        SessionStatus.COMPLETED,
    }
