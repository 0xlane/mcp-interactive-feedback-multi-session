"""
進度通知功能單元測試
==================

測試 FastMCP Context 注入與週期性進度通知（notifications/progress），
驗證避免 Cursor IDE 120 秒空閒超時（Idle Timeout）的機制。
"""

import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Context

from mcp_feedback_enhanced.server import interactive_feedback, mcp
from mcp_feedback_enhanced.web.main import WebUIManager, launch_web_feedback_ui
from mcp_feedback_enhanced.web.models import WebFeedbackSession


class TestProgressNotification:
    """進度通知測試集"""

    @pytest.mark.asyncio
    async def test_tool_schema_hides_context(self):
        """驗證 interactive_feedback 工具 schema 正確隱藏了 ctx 參數"""
        tool = await mcp.get_tool("interactive_feedback")
        assert tool is not None
        properties = tool.parameters.get("properties", {})
        # 應包含一般使用者參數，但絕對不應包含 ctx
        assert "project_directory" in properties
        assert "summary" in properties
        assert "timeout" in properties
        assert "title" in properties
        assert "feedback_session_id" in properties
        assert "ctx" not in properties

    @pytest.mark.asyncio
    async def test_progress_notifications_sent_during_wait(self, tmp_path, monkeypatch):
        """測試在等待回饋期間週期性發送進度通知"""
        # 設置快速進度通知間隔 (0.1 秒)
        monkeypatch.setenv("MCP_PROGRESS_INTERVAL", "0.1")

        mock_ctx = AsyncMock(spec=Context)
        reported_progresses = []

        async def capture_progress(progress, total=None, message=None):
            reported_progresses.append(
                {"progress": progress, "total": total, "message": message}
            )

        mock_ctx.report_progress = AsyncMock(side_effect=capture_progress)

        manager = WebUIManager(is_daemon=True)
        import mcp_feedback_enhanced.web.main as web_main

        orig_manager = web_main._web_ui_manager
        web_main._web_ui_manager = manager

        try:
            # 啟動非同步任務等待回饋
            task = asyncio.create_task(
                launch_web_feedback_ui(
                    str(tmp_path),
                    "測試摘要",
                    timeout=5,
                    title="進度測試",
                    ctx=mock_ctx,
                )
            )

            # 等待 0.35 秒讓進度通知發送數次
            await asyncio.sleep(0.35)

            # 獲取會話並提交回饋
            current_session = manager.get_current_session()
            assert current_session is not None
            await current_session.submit_feedback("已測試通過", [])

            result = await task
            assert result["interactive_feedback"] == "已測試通過"

            # 驗證進度通知有被發送
            assert len(reported_progresses) >= 2
            # 第一筆應為初始 0.0 進度
            assert reported_progresses[0]["progress"] == 0.0
            assert reported_progresses[0]["total"] == 5.0
            assert "已就緒" in reported_progresses[0]["message"]

            # 後續應有帶有已等待時間的進度通知
            assert any("已等待" in p["message"] for p in reported_progresses[1:])

        finally:
            web_main._web_ui_manager = orig_manager

    @pytest.mark.asyncio
    async def test_progress_error_does_not_break_feedback(self, tmp_path, monkeypatch):
        """測試進度通知發送異常時，不影響正常的用戶回饋流程"""
        monkeypatch.setenv("MCP_PROGRESS_INTERVAL", "0.05")

        mock_ctx = AsyncMock(spec=Context)
        mock_ctx.report_progress = AsyncMock(side_effect=RuntimeError("進度傳輸異常"))

        manager = WebUIManager(is_daemon=True)
        import mcp_feedback_enhanced.web.main as web_main

        orig_manager = web_main._web_ui_manager
        web_main._web_ui_manager = manager

        try:
            task = asyncio.create_task(
                launch_web_feedback_ui(
                    str(tmp_path),
                    "測試異常隔離",
                    timeout=5,
                    ctx=mock_ctx,
                )
            )

            await asyncio.sleep(0.15)
            current_session = manager.get_current_session()
            assert current_session is not None
            await current_session.submit_feedback("正常提交", [])

            result = await task
            assert result["interactive_feedback"] == "正常提交"

        finally:
            web_main._web_ui_manager = orig_manager

    @pytest.mark.asyncio
    async def test_none_context_graceful_handling(self, tmp_path):
        """測試 ctx 為 None 時平穩運行無異常"""
        manager = WebUIManager(is_daemon=True)
        import mcp_feedback_enhanced.web.main as web_main

        orig_manager = web_main._web_ui_manager
        web_main._web_ui_manager = manager

        try:
            task = asyncio.create_task(
                launch_web_feedback_ui(
                    str(tmp_path),
                    "無 context 測試",
                    timeout=5,
                    ctx=None,
                )
            )

            await asyncio.sleep(0.05)
            current_session = manager.get_current_session()
            assert current_session is not None
            await current_session.submit_feedback("無 context 提交", [])

            result = await task
            assert result["interactive_feedback"] == "無 context 提交"

        finally:
            web_main._web_ui_manager = orig_manager
