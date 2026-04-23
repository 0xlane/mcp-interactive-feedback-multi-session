#!/usr/bin/env python3
"""
多會話後端單元測試（階段 1）
=============================

驗證 WebUIManager 從「單活躍會話」重構為「多會話並存 + 活躍指針」後的行為：

1. 並發建立多個會話，全部進入 ``sessions`` 字典且不互相干擾；
2. 舊會話在新會話建立後，狀態、feedback_completed、等待任務都保持不變；
3. 活躍指針（``current_session``）在多會話並存下採「粘滯」策略：新會話到達時**不會**強制切走使用者正在看的舊會話，
   只有在舊指針為空 / 指向已移除會話時才會把新會話設為活躍；
4. 單一會話 ``submit_feedback`` 不會解鎖其他會話的 ``wait_for_feedback``；
5. 手動歸檔（cancel_session）能解鎖 ``wait_for_feedback`` 並返回空 dict，
   上層 ``interactive_feedback`` tool 據此返回「用戶取消了反饋」；
6. 活躍會話被歸檔後，活躍指針自動讓出給另一個非終態會話或置空。
"""

from __future__ import annotations

import asyncio

import pytest

from mcp_feedback_enhanced.web.models import SessionStatus, WebFeedbackSession


class TestMultiSessionBackend:
    """WebUIManager 多會話資料結構測試"""

    def test_create_multiple_sessions_coexist(self, web_ui_manager, test_project_dir):
        """建立多個會話後，三者皆存在於 sessions 字典。"""
        sid1 = web_ui_manager.create_session(str(test_project_dir), "任務 1")
        sid2 = web_ui_manager.create_session(str(test_project_dir), "任務 2")
        sid3 = web_ui_manager.create_session(str(test_project_dir), "任務 3")

        assert len({sid1, sid2, sid3}) == 3
        assert len(web_ui_manager.sessions) == 3
        assert sid1 in web_ui_manager.sessions
        assert sid2 in web_ui_manager.sessions
        assert sid3 in web_ui_manager.sessions

    def test_first_session_stays_active_when_new_arrives(
        self, web_ui_manager, test_project_dir
    ):
        """新會話到達時，活躍指針仍停在第一個未歸檔的會話（Phase 3 粘滯語義）。

        這樣避免使用者正在看舊會話時，AI agent 開了一個新會話就把 UI 頁
        強制切走。前端需要時可以透過側欄或 Cmd-1..9 主動切換。
        """
        sid1 = web_ui_manager.create_session(str(test_project_dir), "任務 1")
        sid2 = web_ui_manager.create_session(str(test_project_dir), "任務 2")

        current = web_ui_manager.get_current_session()
        assert current is not None
        assert current.session_id == sid1

        # 兩個會話都保持 WAITING，不被強制推進
        assert web_ui_manager.sessions[sid1].status == SessionStatus.WAITING
        assert web_ui_manager.sessions[sid2].status == SessionStatus.WAITING
        assert not web_ui_manager.sessions[sid1].feedback_completed.is_set()
        assert not web_ui_manager.sessions[sid2].feedback_completed.is_set()

    def test_title_field_is_stored(self, web_ui_manager, test_project_dir):
        """title 參數會被原樣保存到 session 上，可選。"""
        sid_with_title = web_ui_manager.create_session(
            str(test_project_dir), "任務 A", title="修復登錄重定向"
        )
        sid_without_title = web_ui_manager.create_session(str(test_project_dir), "任務 B")

        assert web_ui_manager.sessions[sid_with_title].title == "修復登錄重定向"
        assert web_ui_manager.sessions[sid_without_title].title is None

    def test_current_session_is_property(self, web_ui_manager, test_project_dir):
        """current_session 應為 property：set None 只清指針，不清字典。"""
        sid1 = web_ui_manager.create_session(str(test_project_dir), "任務 1")
        sid2 = web_ui_manager.create_session(str(test_project_dir), "任務 2")

        assert web_ui_manager.current_session is not None
        # Phase 3：新建 sid2 不會覆寫活躍指針，仍是最先建立的 sid1
        assert web_ui_manager.current_session.session_id == sid1

        web_ui_manager.current_session = None
        assert web_ui_manager.current_session is None
        # 字典不受影響
        assert sid1 in web_ui_manager.sessions
        assert sid2 in web_ui_manager.sessions

    def test_new_session_does_not_steal_old_websocket(
        self, web_ui_manager, test_project_dir
    ):
        """Phase 3：HTTP 多工模式下，新會話不會把舊會話的 per-session websocket 搶走。

        事件廣播走 ``manager.broadcast`` 全通道下發，前端按 ``session_id`` 過濾；
        per-session ``websocket`` 欄位只對 ``run_command`` 等老介面還有意義，
        保持各自原本的引用即可。
        """

        class _FakeWS:
            pass

        sid1 = web_ui_manager.create_session(str(test_project_dir), "任務 1")
        ws = _FakeWS()
        web_ui_manager.sessions[sid1].websocket = ws  # type: ignore[assignment]

        sid2 = web_ui_manager.create_session(str(test_project_dir), "任務 2")

        assert web_ui_manager.sessions[sid1].websocket is ws
        assert web_ui_manager.sessions[sid2].websocket is None


class TestSessionCancellation:
    """SessionStatus.CANCELED 與 cancel_session 流程測試"""

    @pytest.mark.asyncio
    async def test_cancel_waiting_session_unblocks_wait_for_feedback(
        self, web_ui_manager, test_project_dir
    ):
        """手動歸檔 WAITING 會話 → wait_for_feedback 返回空 dict（上層視為取消）。"""
        sid = web_ui_manager.create_session(str(test_project_dir), "將被取消的任務")
        session = web_ui_manager.sessions[sid]

        # 並發：一個協程在等待，主協程稍後觸發取消
        wait_task = asyncio.create_task(session.wait_for_feedback(timeout=30))
        # 給等待任務一點時間進入 executor（feedback_completed.wait）
        await asyncio.sleep(0.05)

        ok = web_ui_manager.cancel_session(sid, message="測試手動歸檔")
        assert ok is True

        # 等待任務應快速返回（遠不到 30 秒）
        result = await asyncio.wait_for(wait_task, timeout=5)
        assert result == {}
        assert session.status == SessionStatus.CANCELED
        assert session.feedback_completed.is_set()

    def test_cancel_active_session_transfers_current_pointer(
        self, web_ui_manager, test_project_dir
    ):
        """歸檔當前活躍會話時，活躍指針轉移到字典中其他非終態會話。

        語義：``cancel_session`` 相當於「永久歸檔」，會話會從 ``sessions``
        字典中真正移除（避免刷新後 ``sessions_snapshot`` 又把它推回前端）。
        Phase 3 粘滯語義下，sid1 是初始活躍會話；歸檔 sid1 後指針應轉移到 sid2。
        """
        sid1 = web_ui_manager.create_session(str(test_project_dir), "任務 1")
        sid2 = web_ui_manager.create_session(str(test_project_dir), "任務 2")

        assert web_ui_manager.current_session is not None
        assert web_ui_manager.current_session.session_id == sid1

        ok = web_ui_manager.cancel_session(sid1)
        assert ok

        current_after = web_ui_manager.current_session
        assert current_after is not None
        assert current_after.session_id == sid2
        # sid1 已經被從 sessions 字典中物理移除
        assert sid1 not in web_ui_manager.sessions
        assert sid2 in web_ui_manager.sessions

    def test_cancel_last_active_session_clears_pointer(
        self, web_ui_manager, test_project_dir
    ):
        """若只有一個活躍會話且被歸檔，活躍指針應置空。"""
        sid = web_ui_manager.create_session(str(test_project_dir), "唯一任務")
        ok = web_ui_manager.cancel_session(sid)
        assert ok
        assert web_ui_manager.current_session is None

    def test_cancel_nonexistent_session_returns_false(self, web_ui_manager):
        """歸檔不存在的會話 id 返回 False。"""
        assert web_ui_manager.cancel_session("nonexistent-session-id") is False

    @pytest.mark.asyncio
    async def test_cancel_submitted_session_removes_from_store(
        self, web_ui_manager, test_project_dir
    ):
        """歸檔已送出反饋的會話：狀態不回退，但會從 sessions 字典中物理移除。

        ``submit_feedback`` 會把狀態推進到 ``FEEDBACK_SUBMITTED``。對於已經
        進入終態的會話，``session.cancel()`` 仍會返回 False（因為不會把
        FEEDBACK_SUBMITTED 再回退成 CANCELED），但 ``WebUIManager.cancel_session``
        會把整條 session 從字典中 pop 掉 —— 這是 Phase 3 為了修「清除已完成
        後刷新又回來」bug 的關鍵行為。
        """
        sid = web_ui_manager.create_session(str(test_project_dir), "已提交的任務")
        session = web_ui_manager.sessions[sid]

        await session.submit_feedback("ok", [], {})
        assert session.feedback_completed.is_set()
        assert session.status == SessionStatus.FEEDBACK_SUBMITTED

        ok = web_ui_manager.cancel_session(sid)
        assert ok is True
        # sid 已從字典中移除，即使狀態是 FEEDBACK_SUBMITTED
        assert sid not in web_ui_manager.sessions
        # 底層 session.cancel() 對終態 session 仍返回 False（未重置為 CANCELED）
        assert session.cancel() is False


class TestConcurrentFeedbackIsolation:
    """並發會話互不干擾測試"""

    @pytest.mark.asyncio
    async def test_submit_to_one_session_does_not_affect_others(
        self, web_ui_manager, test_project_dir
    ):
        """對某一會話 submit_feedback 不會解鎖其他會話的 feedback_completed。"""
        sid1 = web_ui_manager.create_session(str(test_project_dir), "任務 1")
        sid2 = web_ui_manager.create_session(str(test_project_dir), "任務 2")
        s1 = web_ui_manager.sessions[sid1]
        s2 = web_ui_manager.sessions[sid2]

        await s2.submit_feedback("已提交任務 2", [], {})

        # s1 保持等待中，feedback_completed 未被觸發
        assert not s1.feedback_completed.is_set()
        assert s1.status == SessionStatus.WAITING
        # s2 已完成狀態推進到 FEEDBACK_SUBMITTED
        assert s2.feedback_completed.is_set()
        assert s2.status == SessionStatus.FEEDBACK_SUBMITTED
        assert s2.feedback_result == "已提交任務 2"

    @pytest.mark.asyncio
    async def test_session_lookup_by_id_after_sticky_active(
        self, web_ui_manager, test_project_dir
    ):
        """回歸測試：粘滯活躍指針下，create_session 之後必須用 session_id 找新會話。

        這是 Phase 3 曾經踩過的雷：``launch_web_feedback_ui`` 以前是
        ``session = manager.get_current_session()`` ——在粘滯語義下，它會返回
        舊活躍會話而非新建的那個，導致新會話的 ``wait_for_feedback`` 其實在
        等舊會話的 feedback_completed，最終兩個 MCP 調用拿到**同一份**反饋。
        這裡用精確的 ``get_session(new_sid)`` 來鎖定目標，不能被
        ``current_session`` 遮蔽。
        """
        sid_old = web_ui_manager.create_session(str(test_project_dir), "舊任務")
        sid_new = web_ui_manager.create_session(str(test_project_dir), "新任務")

        # 粘滯語義：current 仍是 sid_old
        assert web_ui_manager.get_current_session().session_id == sid_old
        # 但按 id 精確查找能拿到新會話
        target_new = web_ui_manager.get_session(sid_new)
        assert target_new is not None
        assert target_new.session_id == sid_new
        assert target_new.summary == "新任務"

        # 對新會話提交反饋，舊會話必須仍處於 WAITING
        await target_new.submit_feedback("只給新任務的反饋", [], {})
        old_session = web_ui_manager.get_session(sid_old)
        assert old_session is not None
        assert not old_session.feedback_completed.is_set()
        assert old_session.status == SessionStatus.WAITING
        assert target_new.feedback_result == "只給新任務的反饋"


class TestSessionStatusEnum:
    """SessionStatus 枚舉擴充驗證"""

    def test_canceled_status_is_terminal(self):
        """CANCELED 應被視作終態。"""
        assert SessionStatus.CANCELED.value == "canceled"
        # 建個孤立 session 直接測試
        s = WebFeedbackSession("sid", "/tmp", "summary")
        assert s.cancel("test") is True
        assert s.is_terminal() is True
        assert s.status == SessionStatus.CANCELED
        assert s.feedback_completed.is_set()

    def test_cannot_cancel_terminal_session(self):
        """終態會話再次 cancel 返回 False。"""
        s = WebFeedbackSession("sid", "/tmp", "summary")
        s.set_expired("expired")
        assert s.cancel() is False
