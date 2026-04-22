#!/usr/bin/env python3
"""
多會話後端單元測試（階段 1）
=============================

驗證 WebUIManager 從「單活躍會話」重構為「多會話並存 + 活躍指針」後的行為：

1. 並發建立多個會話，全部進入 ``sessions`` 字典且不互相干擾；
2. 舊會話在新會話建立後，狀態、feedback_completed、等待任務都保持不變；
3. 僅最新建立的會話為活躍會話（``current_session`` 指向它）；
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

    def test_only_latest_session_is_current(self, web_ui_manager, test_project_dir):
        """活躍指針永遠指向最新建立的會話，舊會話不變為終態。"""
        sid1 = web_ui_manager.create_session(str(test_project_dir), "任務 1")
        sid2 = web_ui_manager.create_session(str(test_project_dir), "任務 2")

        current = web_ui_manager.get_current_session()
        assert current is not None
        assert current.session_id == sid2

        # 舊會話狀態必須保持 WAITING，不被強制推進
        s1 = web_ui_manager.sessions[sid1]
        assert s1.status == SessionStatus.WAITING
        assert not s1.feedback_completed.is_set()

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
        assert web_ui_manager.current_session.session_id == sid2

        web_ui_manager.current_session = None
        assert web_ui_manager.current_session is None
        # 字典不受影響
        assert sid1 in web_ui_manager.sessions
        assert sid2 in web_ui_manager.sessions

    def test_old_session_websocket_transfer(self, web_ui_manager, test_project_dir):
        """建立新會話時，舊活躍會話的 WebSocket 轉移給新會話，且舊會話不再持有。"""

        class _FakeWS:
            pass

        sid1 = web_ui_manager.create_session(str(test_project_dir), "任務 1")
        ws = _FakeWS()
        web_ui_manager.sessions[sid1].websocket = ws  # type: ignore[assignment]

        sid2 = web_ui_manager.create_session(str(test_project_dir), "任務 2")

        assert web_ui_manager.sessions[sid1].websocket is None
        assert web_ui_manager.sessions[sid2].websocket is ws


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
        """歸檔當前活躍會話時，活躍指針轉移到字典中其他非終態會話。"""
        sid1 = web_ui_manager.create_session(str(test_project_dir), "任務 1")
        sid2 = web_ui_manager.create_session(str(test_project_dir), "任務 2")

        assert web_ui_manager.current_session is not None
        assert web_ui_manager.current_session.session_id == sid2

        ok = web_ui_manager.cancel_session(sid2)
        assert ok

        current_after = web_ui_manager.current_session
        assert current_after is not None
        assert current_after.session_id == sid1
        # sid2 仍然在 sessions 字典中，但狀態為 CANCELED
        assert web_ui_manager.sessions[sid2].status == SessionStatus.CANCELED

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
    async def test_cancel_submitted_session_is_noop(
        self, web_ui_manager, test_project_dir
    ):
        """歸檔已送出反饋的會話應為 no-op：狀態不變，session.cancel() 返回 False。

        ``submit_feedback`` 會把狀態推進到 ``FEEDBACK_SUBMITTED``（WAITING 起點時
        自動補一次流轉）。``feedback_completed.is_set()`` 也會在此時被觸發。

        ``WebUIManager.cancel_session`` 返回值表達的是「會話存在且已被處理」，
        它仍返回 True；精確的「是否改變狀態」由 ``session.cancel()`` 的返回值
        反映，這裡直接調用底層方法再驗一遍。
        """
        sid = web_ui_manager.create_session(str(test_project_dir), "已提交的任務")
        session = web_ui_manager.sessions[sid]

        await session.submit_feedback("ok", [], {})
        assert session.feedback_completed.is_set()
        assert session.status == SessionStatus.FEEDBACK_SUBMITTED
        status_before_cancel = session.status

        # manager 層：會話存在，視作已處理（由 UI 刷新列表即可）
        ok = web_ui_manager.cancel_session(sid)
        assert ok is True
        assert session.status == status_before_cancel
        # 底層 session.cancel() 應明確返回 False（未改動狀態）
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
