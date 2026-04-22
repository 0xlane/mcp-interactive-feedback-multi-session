#!/usr/bin/env python3
"""
主要路由處理
============

設置 Web UI 的主要路由和處理邏輯。
"""

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from ... import __version__
from ...debug import web_debug_log as debug_log
from ..constants import get_message_code as get_msg_code


if TYPE_CHECKING:
    from ..main import WebUIManager


def load_user_layout_settings() -> str:
    """載入用戶的佈局模式設定"""
    try:
        # 使用統一的設定檔案路徑
        config_dir = Path.home() / ".config" / "mcp-feedback-enhanced"
        settings_file = config_dir / "ui_settings.json"

        if settings_file.exists():
            with open(settings_file, encoding="utf-8") as f:
                settings = json.load(f)
                layout_mode = settings.get("layoutMode", "combined-vertical")
                debug_log(f"從設定檔案載入佈局模式: {layout_mode}")
                # 修復 no-any-return 錯誤 - 確保返回 str 類型
                return str(layout_mode)
        else:
            debug_log("設定檔案不存在，使用預設佈局模式: combined-vertical")
            return "combined-vertical"
    except Exception as e:
        debug_log(f"載入佈局設定失敗: {e}，使用預設佈局模式: combined-vertical")
        return "combined-vertical"


# 使用統一的訊息代碼系統
# 從 ..constants 導入的 get_msg_code 函數會處理所有訊息代碼
# 舊的 key 會自動映射到新的常量


def setup_routes(manager: "WebUIManager"):
    """設置路由"""

    @manager.app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """統一回饋頁面 - 重構後的主頁面"""
        # 獲取當前活躍會話
        current_session = manager.get_current_session()

        if not current_session:
            # 沒有活躍會話時顯示等待頁面
            return manager.templates.TemplateResponse(
                request,
                "index.html",
                {
                    "title": "MCP Feedback Enhanced",
                    "has_session": False,
                    "version": __version__,
                },
            )

        # 有活躍會話時顯示回饋頁面
        # 載入用戶的佈局模式設定
        layout_mode = load_user_layout_settings()

        return manager.templates.TemplateResponse(
            request,
            "feedback.html",
            {
                "project_directory": current_session.project_directory,
                "summary": current_session.summary,
                "title": "Interactive Feedback - 回饋收集",
                "version": __version__,
                "has_session": True,
                "layout_mode": layout_mode,
            },
        )

    @manager.app.get("/api/translations")
    async def get_translations():
        """獲取翻譯數據 - 從 Web 專用翻譯檔案載入"""
        translations = {}

        # 獲取 Web 翻譯檔案目錄
        web_locales_dir = Path(__file__).parent.parent / "locales"
        supported_languages = ["zh-TW", "zh-CN", "en"]

        for lang_code in supported_languages:
            lang_dir = web_locales_dir / lang_code
            translation_file = lang_dir / "translation.json"

            try:
                if translation_file.exists():
                    with open(translation_file, encoding="utf-8") as f:
                        lang_data = json.load(f)
                        translations[lang_code] = lang_data
                        debug_log(f"成功載入 Web 翻譯: {lang_code}")
                else:
                    debug_log(f"Web 翻譯檔案不存在: {translation_file}")
                    translations[lang_code] = {}
            except Exception as e:
                debug_log(f"載入 Web 翻譯檔案失敗 {lang_code}: {e}")
                translations[lang_code] = {}

        debug_log(f"Web 翻譯 API 返回 {len(translations)} 種語言的數據")
        return JSONResponse(content=translations)

    @manager.app.get("/api/session-status")
    async def get_session_status(request: Request):
        """獲取當前會話狀態"""
        current_session = manager.get_current_session()

        # 從請求頭獲取客戶端語言
        lang = (
            request.headers.get("Accept-Language", "zh-TW").split(",")[0].split("-")[0]
        )
        if lang == "zh":
            lang = "zh-TW"

        if not current_session:
            return JSONResponse(
                content={
                    "has_session": False,
                    "status": "no_session",
                    "messageCode": get_msg_code("no_active_session"),
                }
            )

        return JSONResponse(
            content={
                "has_session": True,
                "status": "active",
                "session_info": {
                    "project_directory": current_session.project_directory,
                    "summary": current_session.summary,
                    "feedback_completed": current_session.feedback_completed.is_set(),
                },
            }
        )

    @manager.app.get("/api/current-session")
    async def get_current_session(request: Request):
        """獲取當前會話詳細信息"""
        current_session = manager.get_current_session()

        # 從查詢參數獲取語言，如果沒有則從會話獲取，最後使用默認值

        if not current_session:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "No active session",
                    "messageCode": get_msg_code("no_active_session"),
                },
            )

        return JSONResponse(
            content={
                "session_id": current_session.session_id,
                "project_directory": current_session.project_directory,
                "summary": current_session.summary,
                "feedback_completed": current_session.feedback_completed.is_set(),
                "command_logs": current_session.command_logs,
                "images_count": len(current_session.images),
            }
        )

    @manager.app.get("/api/all-sessions")
    async def get_all_sessions(request: Request):
        """獲取所有會話的實時狀態（保留兼容路徑，新前端請用 ``/api/sessions``）。"""

        try:
            sessions_data = []

            # 獲取所有會話的實時狀態（附加 has_websocket 用於舊前端的連接探測）
            for session_id, session in manager.sessions.items():
                session_info = {
                    "session_id": session.session_id,
                    "project_directory": session.project_directory,
                    "summary": session.summary,
                    "title": session.title,  # 階段 1 新增：AI 傳入的會話標題（可能為 None）
                    "status": session.status.value,
                    "status_message": session.status_message,
                    "created_at": int(session.created_at * 1000),  # 轉換為毫秒
                    "last_activity": int(session.last_activity * 1000),
                    "feedback_completed": session.feedback_completed.is_set(),
                    "has_websocket": session.websocket is not None,
                    "is_current": session == manager.current_session,
                    "user_messages": session.user_messages,  # 包含用戶消息記錄
                }
                sessions_data.append(session_info)

            # 按創建時間排序（最新的在前）
            sessions_data.sort(key=lambda x: x["created_at"], reverse=True)

            debug_log(f"返回 {len(sessions_data)} 個會話的實時狀態")
            return JSONResponse(content={"sessions": sessions_data})

        except Exception as e:
            debug_log(f"獲取所有會話狀態失敗: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Failed to get sessions: {e!s}",
                    "messageCode": get_msg_code("get_sessions_failed"),
                },
            )

    @manager.app.get("/api/sessions")
    async def get_sessions(request: Request):
        """獲取所有會話（多路復用 UI 主數據源）。

        - 返回 ``sessions_snapshot`` 事件同款的快照字段；
        - 附帶 ``active_session_id`` 與 ``connected_clients`` 便於前端一次拿齊渲染狀態；
        - 語義與 ``/api/all-sessions`` 完全等價，字段名略有差異（無 ``has_websocket``，
          改為全局 ``connected_clients``）。
        """
        try:
            snapshot = manager.build_sessions_snapshot()
            return JSONResponse(
                content={
                    "sessions": snapshot,
                    "active_session_id": manager._active_session_id,
                    "connected_clients": len(manager.connections),
                }
            )
        except Exception as e:  # noqa: BLE001
            debug_log(f"獲取會話快照失敗: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Failed to get sessions: {e!s}",
                    "messageCode": get_msg_code("get_sessions_failed"),
                },
            )

    @manager.app.delete("/api/sessions")
    async def delete_sessions_by_status(request: Request):
        """批量刪除指定狀態的會話（由 UI 的「清空已完成」按鈕使用）。

        Query 參數：
        - ``status``：要清理的狀態枚舉值（``completed`` / ``timeout`` / ``expired`` /
          ``canceled`` / ``error`` / ``all_terminal``）。``all_terminal`` 表示所有
          終態（相當於前端的「清空已完成/已取消/已超時」複合動作）。

        注意：``WAITING`` / ``ACTIVE`` / ``FEEDBACK_SUBMITTED`` 不可在此接口批量刪除，
        需通過 ``POST /api/sessions/{sid}/archive`` 單獨歸檔。
        """
        status_param = request.query_params.get("status", "").strip().lower()
        if not status_param:
            return JSONResponse(
                status_code=400,
                content={"error": "missing 'status' query parameter"},
            )

        # 終態集合（多選）
        from ..models.feedback_session import SessionStatus

        terminal_statuses = {
            SessionStatus.COMPLETED,
            SessionStatus.TIMEOUT,
            SessionStatus.EXPIRED,
            SessionStatus.CANCELED,
            SessionStatus.ERROR,
        }

        if status_param == "all_terminal":
            target_set = terminal_statuses
        else:
            try:
                target = SessionStatus(status_param)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"error": f"invalid status: {status_param}"},
                )
            if target not in terminal_statuses:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": (
                            f"status '{status_param}' is not terminal; use "
                            "POST /api/sessions/{id}/archive instead"
                        )
                    },
                )
            target_set = {target}

        to_remove = [
            sid for sid, s in manager.sessions.items() if s.status in target_set
        ]
        for sid in to_remove:
            try:
                manager.remove_session(sid)
                await manager.broadcast_session_event("session_removed", sid)
            except Exception as e:  # noqa: BLE001
                debug_log(f"批量刪除會話 {sid} 失敗: {e}")

        return JSONResponse(
            content={
                "status": "success",
                "removed": to_remove,
                "count": len(to_remove),
            }
        )

    @manager.app.post("/api/sessions/{session_id}/archive")
    async def archive_session(session_id: str, request: Request):
        """手動歸檔會話（階段 1 新增，多會話模式）。

        行為依會話當前狀態而定：
        - WAITING / ACTIVE：呼叫 ``session.cancel()`` 解鎖 ``wait_for_feedback``，
          對應的 MCP tool 呼叫會返回「用戶取消了反饋」給 AI Agent。
        - FEEDBACK_SUBMITTED / 終態：僅視作 UI 層歸檔，不變動狀態。

        若歸檔的是當前活躍會話，活躍指針會自動轉給另一個非終態會話（或置空）。
        """
        try:
            # 可選：body 中可帶 reason 作為歸檔原因
            reason: str | None = None
            try:
                body = await request.json()
                if isinstance(body, dict):
                    raw = body.get("reason")
                    if isinstance(raw, str) and raw.strip():
                        reason = raw.strip()
            except Exception:
                reason = None

            message = reason or "使用者已手動歸檔此會話"

            if session_id not in manager.sessions:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "Session not found",
                        "session_id": session_id,
                    },
                )

            session = manager.sessions[session_id]
            previous_status = session.status.value

            ok = manager.cancel_session(session_id, message=message)
            if not ok:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "Failed to archive session",
                        "session_id": session_id,
                    },
                )

            # 廣播 session_archived 給所有已連接的瀏覽器 Tab，讓側欄即時更新
            await manager.broadcast_session_event(
                "session_archived",
                session_id,
                previous_status=previous_status,
                reason=message,
            )

            debug_log(
                f"會話 {session_id} 已歸檔（previous={previous_status}, "
                f"current={session.status.value}）"
            )
            return JSONResponse(
                content={
                    "status": "success",
                    "session_id": session_id,
                    "previous_status": previous_status,
                    "current_status": session.status.value,
                }
            )

        except Exception as e:
            debug_log(f"歸檔會話 {session_id} 失敗: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Archive failed: {e!s}",
                },
            )

    @manager.app.post("/api/add-user-message")
    async def add_user_message(request: Request):
        """添加用戶消息到當前會話"""

        try:
            data = await request.json()
            current_session = manager.get_current_session()

            if not current_session:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "No active session",
                        "messageCode": get_msg_code("no_active_session"),
                    },
                )

            # 添加用戶消息到會話
            current_session.add_user_message(data)

            debug_log(f"用戶消息已添加到會話 {current_session.session_id}")
            return JSONResponse(
                content={
                    "status": "success",
                    "messageCode": get_msg_code("user_message_recorded"),
                }
            )

        except Exception as e:
            debug_log(f"添加用戶消息失敗: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Failed to add user message: {e!s}",
                    "messageCode": get_msg_code("add_user_message_failed"),
                },
            )

    @manager.app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, lang: str = "zh-TW"):
        """WebSocket 多路復用端點（階段 3）。

        一條 ``/ws`` 連接對應一個瀏覽器 Tab；會話事件通過消息中的 ``session_id``
        字段路由。連接建立即推送 ``sessions_snapshot`` 全量快照，之後新增/狀態變更/
        歸檔等以 ``session_*`` 事件廣播到**所有**連接（前端按 ``session_id`` 分派）。

        向下兼容：
        - 若客戶端消息不帶 ``session_id``，服務端回退到 ``manager.get_current_session()``；
        - ``connection_established`` 仍會發送；
        - 舊的 ``session_updated{action:"new_session_created"}`` 在本版本保留以便
          舊前端在遷移期仍能工作，待 Phase 3 前端上線後可於後續版本移除。
        """
        await websocket.accept()

        manager.register_connection(websocket)
        debug_log(
            f"WebSocket 多路復用連接已接受 (lang={lang})，當前連接數 {len(manager.connections)}"
        )

        # 連接建立：
        # 1) 先發 connection_established（舊前端兼容，保持其為首條消息）
        # 2) 再發 sessions_snapshot（新多會話前端用）
        try:
            await websocket.send_json(
                {
                    "type": "connection_established",
                    "messageCode": get_msg_code("websocket_connected"),
                }
            )
            await websocket.send_json(
                {
                    "type": "sessions_snapshot",
                    "sessions": manager.build_sessions_snapshot(),
                    "active_session_id": manager._active_session_id,
                }
            )

            # 舊前端兼容：若存在 _pending_session_update，推一個
            # session_updated 事件（用當前活躍會話填充）
            if getattr(manager, "_pending_session_update", False):
                current = manager.get_current_session()
                if current is not None:
                    await websocket.send_json(
                        {
                            "type": "session_updated",
                            "action": "new_session_created",
                            "messageCode": get_msg_code("new_session_created"),
                            "session_info": {
                                "project_directory": current.project_directory,
                                "summary": current.summary,
                                "session_id": current.session_id,
                            },
                        }
                    )
                    manager._pending_session_update = False
                    debug_log("✅ 已發送會話更新通知到前端")

            # 舊前端兼容：若存在當前會話，將其 websocket 指向本連接，
            # 這樣舊前端不帶 session_id 的 submit_feedback/run_command 仍能命中
            current = manager.get_current_session()
            if current is not None:
                current.websocket = websocket
                # 同時推送 status_update 以保留舊路徑
                await websocket.send_json(
                    {
                        "type": "status_update",
                        "session_id": current.session_id,
                        "status_info": current.get_status_info(),
                    }
                )

        except Exception as e:  # noqa: BLE001
            debug_log(f"發送 sessions_snapshot / 連接確認失敗: {e}")

        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                await handle_websocket_message_mux(manager, websocket, message)
        except WebSocketDisconnect:
            debug_log("WebSocket 連接正常斷開")
        except ConnectionResetError:
            debug_log("WebSocket 連接被重置")
        except Exception as e:  # noqa: BLE001
            debug_log(f"WebSocket 錯誤: {e}")
        finally:
            manager.unregister_connection(websocket)

    @manager.app.post("/api/save-settings")
    async def save_settings(request: Request):
        """保存設定到檔案"""

        try:
            data = await request.json()

            # 使用統一的設定檔案路徑
            config_dir = Path.home() / ".config" / "mcp-feedback-enhanced"
            config_dir.mkdir(parents=True, exist_ok=True)
            settings_file = config_dir / "ui_settings.json"

            # 保存設定到檔案
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            debug_log(f"設定已保存到: {settings_file}")

            return JSONResponse(
                content={
                    "status": "success",
                    "messageCode": get_msg_code("settings_saved"),
                }
            )

        except Exception as e:
            debug_log(f"保存設定失敗: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Save failed: {e!s}",
                    "messageCode": get_msg_code("save_failed"),
                },
            )

    @manager.app.get("/api/load-settings")
    async def load_settings(request: Request):
        """從檔案載入設定"""

        try:
            # 使用統一的設定檔案路徑
            config_dir = Path.home() / ".config" / "mcp-feedback-enhanced"
            settings_file = config_dir / "ui_settings.json"

            if settings_file.exists():
                with open(settings_file, encoding="utf-8") as f:
                    settings = json.load(f)

                debug_log(f"設定已從檔案載入: {settings_file}")
                return JSONResponse(content=settings)
            debug_log("設定檔案不存在，返回空設定")
            return JSONResponse(content={})

        except Exception as e:
            debug_log(f"載入設定失敗: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Load failed: {e!s}",
                    "messageCode": get_msg_code("load_failed"),
                },
            )

    @manager.app.post("/api/clear-settings")
    async def clear_settings(request: Request):
        """清除設定檔案"""

        try:
            # 使用統一的設定檔案路徑
            config_dir = Path.home() / ".config" / "mcp-feedback-enhanced"
            settings_file = config_dir / "ui_settings.json"

            if settings_file.exists():
                settings_file.unlink()
                debug_log(f"設定檔案已刪除: {settings_file}")
            else:
                debug_log("設定檔案不存在，無需刪除")

            return JSONResponse(
                content={
                    "status": "success",
                    "messageCode": get_msg_code("settings_cleared"),
                }
            )

        except Exception as e:
            debug_log(f"清除設定失敗: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Clear failed: {e!s}",
                    "messageCode": get_msg_code("clear_failed"),
                },
            )

    @manager.app.get("/api/load-session-history")
    async def load_session_history(request: Request):
        """從檔案載入會話歷史"""

        try:
            # 使用統一的設定檔案路徑
            config_dir = Path.home() / ".config" / "mcp-feedback-enhanced"
            history_file = config_dir / "session_history.json"

            if history_file.exists():
                with open(history_file, encoding="utf-8") as f:
                    history_data = json.load(f)

                debug_log(f"會話歷史已從檔案載入: {history_file}")

                # 確保資料格式相容性
                if isinstance(history_data, dict):
                    # 新格式：包含版本資訊和其他元資料
                    sessions = history_data.get("sessions", [])
                    last_cleanup = history_data.get("lastCleanup", 0)
                else:
                    # 舊格式：直接是會話陣列（向後相容）
                    sessions = history_data if isinstance(history_data, list) else []
                    last_cleanup = 0

                # 回傳會話歷史資料
                return JSONResponse(
                    content={"sessions": sessions, "lastCleanup": last_cleanup}
                )

            debug_log("會話歷史檔案不存在，返回空歷史")
            return JSONResponse(content={"sessions": [], "lastCleanup": 0})

        except Exception as e:
            debug_log(f"載入會話歷史失敗: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Load failed: {e!s}",
                    "messageCode": get_msg_code("load_failed"),
                },
            )

    @manager.app.post("/api/save-session-history")
    async def save_session_history(request: Request):
        """保存會話歷史到檔案"""

        try:
            data = await request.json()

            # 使用統一的設定檔案路徑
            config_dir = Path.home() / ".config" / "mcp-feedback-enhanced"
            config_dir.mkdir(parents=True, exist_ok=True)
            history_file = config_dir / "session_history.json"

            # 建立新格式的資料結構
            history_data = {
                "version": "1.0",
                "sessions": data.get("sessions", []),
                "lastCleanup": data.get("lastCleanup", 0),
                "savedAt": int(time.time() * 1000),  # 當前時間戳
            }

            # 保存會話歷史到檔案
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history_data, f, ensure_ascii=False, indent=2)

            debug_log(f"會話歷史已保存到: {history_file}")
            session_count = len(history_data["sessions"])
            debug_log(f"保存了 {session_count} 個會話記錄")

            return JSONResponse(
                content={
                    "status": "success",
                    "messageCode": get_msg_code("session_history_saved"),
                    "params": {"count": session_count},
                }
            )

        except Exception as e:
            debug_log(f"保存會話歷史失敗: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Save failed: {e!s}",
                    "messageCode": get_msg_code("save_failed"),
                },
            )

    @manager.app.get("/api/log-level")
    async def get_log_level(request: Request):
        """獲取日誌等級設定"""

        try:
            # 使用統一的設定檔案路徑
            config_dir = Path.home() / ".config" / "mcp-feedback-enhanced"
            settings_file = config_dir / "ui_settings.json"

            if settings_file.exists():
                with open(settings_file, encoding="utf-8") as f:
                    settings_data = json.load(f)
                    log_level = settings_data.get("logLevel", "INFO")
                    debug_log(f"從設定檔案載入日誌等級: {log_level}")
                    return JSONResponse(content={"logLevel": log_level})
            else:
                # 預設日誌等級
                default_log_level = "INFO"
                debug_log(f"使用預設日誌等級: {default_log_level}")
                return JSONResponse(content={"logLevel": default_log_level})

        except Exception as e:
            debug_log(f"獲取日誌等級失敗: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Failed to get log level: {e!s}",
                    "messageCode": get_msg_code("get_log_level_failed"),
                },
            )

    @manager.app.post("/api/log-level")
    async def set_log_level(request: Request):
        """設定日誌等級"""

        try:
            data = await request.json()
            log_level = data.get("logLevel")

            if not log_level or log_level not in ["DEBUG", "INFO", "WARN", "ERROR"]:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Invalid log level",
                        "messageCode": get_msg_code("invalid_log_level"),
                    },
                )

            # 使用統一的設定檔案路徑
            config_dir = Path.home() / ".config" / "mcp-feedback-enhanced"
            config_dir.mkdir(parents=True, exist_ok=True)
            settings_file = config_dir / "ui_settings.json"

            # 載入現有設定或創建新設定
            settings_data = {}
            if settings_file.exists():
                with open(settings_file, encoding="utf-8") as f:
                    settings_data = json.load(f)

            # 更新日誌等級
            settings_data["logLevel"] = log_level

            # 保存設定到檔案
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(settings_data, f, ensure_ascii=False, indent=2)

            debug_log(f"日誌等級已設定為: {log_level}")

            return JSONResponse(
                content={
                    "status": "success",
                    "logLevel": log_level,
                    "messageCode": get_msg_code("log_level_updated"),
                }
            )

        except Exception as e:
            debug_log(f"設定日誌等級失敗: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Set failed: {e!s}",
                    "messageCode": get_msg_code("set_failed"),
                },
            )


async def handle_websocket_message_mux(
    manager: "WebUIManager", websocket: "WebSocket", data: dict
):
    """處理多路復用 WebSocket 消息（階段 3）。

    路由規則：
    1. ``data["session_id"]`` 存在且在 ``manager.sessions`` 中 → 路由到該 session；
    2. 否則回退到 ``manager.get_current_session()``（舊前端兼容）；
    3. ``heartbeat`` / ``pong`` 不需要 session，直接在連接層處理。
    """
    message_type = data.get("type")
    session_id = data.get("session_id")

    target_session = None
    if session_id:
        target_session = manager.sessions.get(session_id)
        if target_session is None:
            debug_log(
                f"未找到 session_id={session_id} 對應的會話，忽略 type={message_type}"
            )
            try:
                await websocket.send_json(
                    {
                        "type": "error",
                        "session_id": session_id,
                        "error_code": "session_not_found",
                        "message": f"Session {session_id} not found",
                    }
                )
            except Exception:
                pass
            return
        # 將本連接記為該會話「最近的 WebSocket」，老接口如 `run_command` 讀寫 session.websocket
        # 時能命中；真正的事件發送走 manager.broadcast，與此無關。
        target_session.websocket = websocket
    else:
        target_session = manager.get_current_session()

    # ------- 不需要 session 的消息 -------
    if message_type == "heartbeat":
        if target_session is not None:
            target_session.last_heartbeat = time.time()
            target_session.last_activity = time.time()
        try:
            await websocket.send_json(
                {
                    "type": "heartbeat_response",
                    "timestamp": data.get("timestamp", 0),
                }
            )
        except Exception as e:  # noqa: BLE001
            debug_log(f"發送心跳回應失敗: {e}")
        return

    if message_type == "pong":
        debug_log(f"收到 pong 回應，時間戳: {data.get('timestamp', 'N/A')}")
        return

    if message_type == "get_sessions_snapshot":
        # 前端主動要求全量快照（例如懷疑狀態漂移時）
        try:
            await websocket.send_json(
                {
                    "type": "sessions_snapshot",
                    "sessions": manager.build_sessions_snapshot(),
                    "active_session_id": manager._active_session_id,
                }
            )
        except Exception as e:  # noqa: BLE001
            debug_log(f"推送 sessions_snapshot 失敗: {e}")
        return

    # ------- 以下類型需要目標 session -------
    if target_session is None:
        debug_log(
            f"消息 type={message_type} 無可路由會話（未指定 session_id 且無活躍會話），忽略"
        )
        return

    if message_type == "submit_feedback":
        feedback = data.get("feedback", "")
        images = data.get("images", [])
        settings = data.get("settings", {})
        await target_session.submit_feedback(feedback, images, settings)

    elif message_type == "run_command":
        command = data.get("command", "")
        if command.strip():
            await target_session.run_command(command)

    elif message_type == "get_status":
        try:
            await websocket.send_json(
                {
                    "type": "status_update",
                    "session_id": target_session.session_id,
                    "status_info": target_session.get_status_info(),
                }
            )
        except Exception as e:  # noqa: BLE001
            debug_log(f"發送狀態更新失敗: {e}")

    elif message_type in ("archive_session", "cancel_session"):
        reason = data.get("reason") or "使用者從 UI 歸檔此會話"
        previous_status = target_session.status.value
        ok = manager.cancel_session(target_session.session_id, message=reason)
        if ok:
            await manager.broadcast_session_event(
                "session_archived",
                target_session.session_id,
                previous_status=previous_status,
                reason=reason,
            )
        # 單點發送 ack 給發起方，讓前端能區分「我的請求成功」vs「被動收到他人的廣播」
        try:
            await websocket.send_json(
                {
                    "type": "session_archive_ack",
                    "session_id": target_session.session_id,
                    "ok": ok,
                    "previous_status": previous_status,
                    "current_status": target_session.status.value,
                }
            )
        except Exception as e:  # noqa: BLE001
            debug_log(f"發送 session_archive_ack 失敗: {e}")
        debug_log(
            f"[WS] 會話 {target_session.session_id} 歸檔請求 ok={ok} "
            f"(prev={previous_status}, now={target_session.status.value})"
        )

    elif message_type == "user_timeout":
        debug_log(f"收到用戶超時通知: {target_session.session_id}")
        await target_session._cleanup_resources_on_timeout()

    elif message_type == "update_timeout_settings":
        settings = data.get("settings", {})
        debug_log(f"收到超時設定更新: {settings}")
        if settings.get("enabled"):
            target_session.update_timeout_settings(
                enabled=True, timeout_seconds=settings.get("seconds", 3600)
            )
        else:
            target_session.update_timeout_settings(enabled=False)

    else:
        debug_log(f"未知的消息類型: {message_type}")


# 舊 API 別名：少量單元測試仍以 session 作參數呼叫它；內部委派到 mux 版本。
async def handle_websocket_message(manager: "WebUIManager", session, data: dict):
    """兼容舊接口：把 session.websocket 當 WS 連接委派到 mux handler。

    新碼一律使用 :func:`handle_websocket_message_mux`。
    """
    ws = getattr(session, "websocket", None)
    if ws is None:
        debug_log("handle_websocket_message 舊接口呼叫時 session.websocket 為空，忽略")
        return
    # 若呼叫方未傳 session_id，強制補上，確保 mux 路由能命中
    if not data.get("session_id"):
        data = dict(data)
        data["session_id"] = session.session_id
    await handle_websocket_message_mux(manager, ws, data)


async def _delayed_server_stop(manager: "WebUIManager"):
    """延遲停止服務器"""
    import asyncio

    await asyncio.sleep(5)  # 等待 5 秒讓前端有時間關閉
    from ..main import stop_web_ui

    stop_web_ui()
    debug_log("Web UI 服務器已因用戶超時而停止")
