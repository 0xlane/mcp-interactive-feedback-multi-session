#!/usr/bin/env python3
"""
HTTP Daemon
===========

守護進程入口，負責將以下組件合併為一個 ASGI 應用，並以 uvicorn 前台運行：

- :mod:`mcp_feedback_enhanced.server` 中由 ``FastMCP`` 建立的 MCP 服務
  （透過 ``mcp.http_app()`` 以 Streamable HTTP 暴露於 ``/mcp`` 路徑）；
- :mod:`mcp_feedback_enhanced.web.main` 中的 ``WebUIManager``，承載 Web UI
  與 ``/ws`` / ``/api/...`` 等介面。

與階段 1（stdio）相比的差異：
1. 單一長駐進程，固定綁定 ``127.0.0.1:8765``（可由 CLI 覆寫），
   不再做自動端口遞增；
2. 不主動打開瀏覽器，也不在背景啟動額外 uvicorn 線程 —— 入口即 uvicorn。

設計原則：
- 本模組不依賴 `__main__.py`，便於在測試中直接 `import` 後啟動一個臨時
  daemon；命令列包裝留給 :mod:`__main__`。
- 初始化過程中任何關鍵失敗（PID 鎖衝突、端口佔用等）都會儘早拋出，而非靜默
  退化。
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

import uvicorn

from .debug import server_debug_log as debug_log


if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "build_daemon_app",
    "serve_http",
]


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

_logger = logging.getLogger("uvicorn.error")


def _import_mcp_instance() -> Any:
    """Lazy-import 全域 ``mcp`` 物件（延遲到函數呼叫才引入以避免循環）。"""
    from . import server as server_module

    return server_module.mcp


def build_daemon_app(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> tuple["FastAPI", Any]:
    """建構 daemon 模式下的 FastAPI 應用。

    Args:
        host: 綁定主機（僅用於 WebUIManager 內部記錄 ``server_url``）。
        port: 綁定端口（僅用於內部記錄）。

    Returns:
        ``(app, manager)`` 二元組；``app`` 是可交給 uvicorn 的 ASGI 應用，
        ``manager`` 是內部 :class:`WebUIManager` 實例（暴露給測試或做進一步
        攔截）。
    """
    from .web.main import WebUIManager, set_web_ui_manager

    mcp = _import_mcp_instance()

    mcp_app = mcp.http_app(path="/")

    # Holder：combined_lifespan 在 manager 之前定義，用 holder 後綁定
    manager_holder: dict[str, Any] = {}

    @asynccontextmanager
    async def combined_lifespan(app: "FastAPI") -> AsyncIterator[None]:
        """外層 FastAPI 的 lifespan：把 MCP sub-app 的 lifespan 接進來。

        - startup: 把 MCP ``streamable_http_session_manager`` 啟動；
        - shutdown: 先 broadcast ``shutting_down`` 讓前端 tab 顯示斷線提示，
          再走 MCP 的關閉流程。
        """
        async with mcp_app.lifespan(app):
            debug_log("daemon lifespan started: MCP session manager online")
            try:
                yield
            finally:
                mgr = manager_holder.get("manager")
                if mgr is not None:
                    try:
                        await mgr.broadcast_to_active_tabs(
                            {
                                "type": "shutting_down",
                                "messageCode": "daemon.shuttingDown",
                                "reason": "daemon-stop",
                            }
                        )
                    except Exception as e:  # noqa: BLE001
                        debug_log(f"shutting_down 廣播失敗（可忽略）：{e}")
                debug_log("daemon lifespan ending: MCP session manager offline")

    manager = WebUIManager(
        host=host,
        port=port,
        is_daemon=True,
        lifespan=combined_lifespan,
    )
    manager_holder["manager"] = manager
    # 將 daemon 專用 manager 注入為全域實例，確保 interactive_feedback tool
    # 在 launch_web_feedback_ui 中取得的是同一個 manager（帶 is_daemon 旗標）。
    set_web_ui_manager(manager)

    # 在 MCP sub-app 外包一層日誌：僅在客戶端連接/斷開時打印 INFO
    original_mcp_app = mcp_app
    _known_mcp_sessions: set[str] = set()

    async def mcp_logging_middleware(scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            from starlette.requests import Request as _Req
            req = _Req(scope, receive)
            session_hdr = req.headers.get("mcp-session-id")
            method = req.method

            if method == "DELETE" and session_hdr:
                _logger.info("[MCP] client disconnected (session=%s)", session_hdr)
                _known_mcp_sessions.discard(session_hdr)

            async def send_wrapper(message: dict) -> None:
                if message.get("type") == "http.response.start":
                    headers = dict(
                        (k.decode() if isinstance(k, bytes) else k,
                         v.decode() if isinstance(v, bytes) else v)
                        for k, v in message.get("headers", [])
                    )
                    resp_sid = headers.get("mcp-session-id")
                    if resp_sid and resp_sid not in _known_mcp_sessions:
                        _known_mcp_sessions.add(resp_sid)
                        _logger.info("[MCP] new client connected (session=%s)", resp_sid)
                await send(message)

            await original_mcp_app(scope, receive, send_wrapper)
            return

        await original_mcp_app(scope, receive, send)

    manager.app.mount("/mcp", mcp_logging_middleware)
    debug_log(f"Mounted MCP sub-app at /mcp (host={host}, port={port})")

    return manager.app, manager


def serve_http(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    log_level: str = "info",
) -> None:
    """以前台方式啟動 HTTP daemon。函式返回即表示 daemon 已退出。

    Args:
        host: 綁定主機，預設 ``127.0.0.1``。
        port: 綁定端口，預設 ``8765``。
        log_level: uvicorn 日誌級別。
    """
    debug_log(f"starting daemon on {host}:{port} (pid={os.getpid()})")

    app, _manager = build_daemon_app(host=host, port=port)

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level=log_level,
        access_log=False,
        ws="auto",
        timeout_graceful_shutdown=2,
    )
    server = uvicorn.Server(config)
    server.run()
    debug_log("daemon exited")
