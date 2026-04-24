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
1. 單一長駐進程，由 :class:`~mcp_feedback_enhanced.utils.pid_lock.DaemonPidLock`
   保證同一時刻僅有一個實例在運行；
2. 固定綁定 ``127.0.0.1:8765``（可由 CLI 覆寫），不再做自動端口遞增；
3. 不主動打開瀏覽器，也不在背景啟動額外 uvicorn 線程 —— 入口即 uvicorn。

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
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator

import uvicorn

from .debug import server_debug_log as debug_log
from .utils.pid_lock import AlreadyRunningError, DaemonPidLock


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

_logger = logging.getLogger(__name__)


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
          再走 MCP 的關閉流程；PID 文件由 :class:`DaemonPidLock` 的 atexit
          與 signal handler 鏈負責清理。
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

    manager.app.mount("/mcp", mcp_app)
    debug_log(f"Mounted MCP sub-app at /mcp (host={host}, port={port})")

    return manager.app, manager


def serve_http(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    log_level: str = "info",
    pid_path: Path | None = None,
) -> None:
    """以前台方式啟動 HTTP daemon。函式返回即表示 daemon 已退出。

    Args:
        host: 綁定主機，預設 ``127.0.0.1``。
        port: 綁定端口，預設 ``8765``。
        log_level: uvicorn 日誌級別。
        pid_path: PID 文件路徑，``None`` 表示使用
            :func:`~mcp_feedback_enhanced.utils.pid_lock.default_pid_path`。

    Raises:
        AlreadyRunningError: 同一 PID 文件已被另一個存活進程佔用。
    """
    lock = DaemonPidLock(pid_path)
    try:
        lock.acquire()
    except AlreadyRunningError as exc:
        # 直接上拋，由 CLI 層轉成非零退出碼 + 友好訊息
        raise

    debug_log(
        f"PID lock acquired (pid={os.getpid()}, path={lock.path}); "
        f"starting daemon on {host}:{port}"
    )

    try:
        app, _manager = build_daemon_app(host=host, port=port)

        config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_level=log_level,
            access_log=False,
            ws="auto",
            timeout_graceful_shutdown=0,
        )
        server = uvicorn.Server(config)
        server.run()
    finally:
        lock.release()
        debug_log("daemon exited; PID lock released")
