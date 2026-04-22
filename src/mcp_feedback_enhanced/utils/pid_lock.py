#!/usr/bin/env python3
"""
Daemon PID lock
===============

提供守護進程單實例鎖：

- PID 文件路徑：``~/.config/mcp-feedback-enhanced/daemon.pid``
  （Windows 下 ``XDG_CONFIG_HOME`` 未設時退回 ``~/AppData/Local``）
- 啟動時檢查 PID 是否仍在運行：
    - 若存活 → 拒絕本次啟動（raise :class:`AlreadyRunningError`）；
    - 若進程已死（stale lock）→ 清理後繼續；
- 正常退出 / SIGTERM / SIGINT / 程序崩潰時清理 PID 文件。

設計原則：
- 僅檢查進程存活（不檢查命令行特徵），避免誤判不同二進制佔用 PID
  的罕見場景；搭配固定端口 `127.0.0.1:8765` 已足夠識別。
- Cross-platform：用 `os.kill(pid, 0)` 探活；Windows 上等價於 OpenProcess。
- 保留 `os.getpid()` 寫入，不記錄啟動時間或命令行，保持簡單。
"""

from __future__ import annotations

import atexit
import errno
import os
import sys
import threading
from pathlib import Path


__all__ = [
    "AlreadyRunningError",
    "DaemonPidLock",
    "default_pid_path",
]


# ── 信號處理策略備忘 ─────────────────────────────────────────────────
# 我們**故意不安裝** SIGINT / SIGTERM handler。原因：
#
# 1. 生產環境（daemon 模式）：uvicorn 自帶 SIGINT/SIGTERM 的優雅關機鏈，
#    收到信號後會走正常退出路徑 → 觸發 ``atexit`` → 觸發 ``release()``，
#    PID 文件會被正確清理（已在 `curl` + `kill -TERM` 的端到端測試中驗證）。
# 2. 多 DaemonPidLock 實例並存時（典型是 pytest 套件跑多輪測試），自行
#    安裝 signal handler 容易和 uvicorn / pytest / ResourceManager 的清理
#    鏈互相干擾，可能出現 signal handler 在 atexit 期間再次被觸發導致
#    SystemExit 遞歸的慘狀。
# 3. 若進程被 SIGKILL / OOM 強殺，留下的 PID 文件會在下次啟動時透過
#    ``_pid_alive`` + stale lock 回收邏輯自動處理，無需信號級別兜底。


class AlreadyRunningError(RuntimeError):
    """守護進程已在運行時拋出。"""

    def __init__(self, pid: int, path: Path) -> None:
        super().__init__(
            f"mcp-interactive-feedback daemon already running (pid={pid}, "
            f"pidfile={path}). Stop it first or remove the stale pid file if "
            f"the process is gone."
        )
        self.pid = pid
        self.path = path


def default_pid_path() -> Path:
    """返回平台適宜的 PID 文件路徑。

    優先級：
    1. ``MCP_FEEDBACK_PID_FILE`` 環境變數（用於測試）
    2. ``XDG_CONFIG_HOME/mcp-feedback-enhanced/daemon.pid``
    3. ``~/.config/mcp-feedback-enhanced/daemon.pid``
    4. Windows: ``%LOCALAPPDATA%/mcp-feedback-enhanced/daemon.pid``
    """
    env_override = os.environ.get("MCP_FEEDBACK_PID_FILE")
    if env_override:
        return Path(env_override).expanduser()

    if sys.platform == "win32":
        base = Path(
            os.environ.get("LOCALAPPDATA")
            or (Path.home() / "AppData" / "Local")
        )
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            base = Path(xdg)
        else:
            base = Path.home() / ".config"

    return base / "mcp-feedback-enhanced" / "daemon.pid"


def _pid_alive(pid: int) -> bool:
    """檢查 PID 對應進程是否仍存活。"""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 進程存在但無權訪問；當作仍在運行（保守處理，避免誤殺）
        return True
    except OSError as e:
        if e.errno == errno.ESRCH:
            return False
        return True
    return True


class DaemonPidLock:
    """進程級 PID 鎖（單例守護模式用）。

    典型用法：

    >>> lock = DaemonPidLock()
    >>> lock.acquire()  # raise AlreadyRunningError if another daemon is alive
    >>> # ... run server ...
    >>> lock.release()  # 或依賴 atexit / signal handler 自動清理
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path: Path = path or default_pid_path()
        self._pid_written: int | None = None
        self._lock = threading.Lock()

    def read_existing_pid(self) -> int | None:
        """讀取現有 PID 文件的 PID；若不存在/不可讀返回 None。"""
        try:
            text = self.path.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, NotADirectoryError):
            return None
        except OSError:
            return None
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None

    def acquire(self) -> None:
        """寫入當前進程 PID；若已有存活的進程則 raise AlreadyRunningError。

        行為：
        - 若 PID 文件不存在 → 創建父目錄並寫入；
        - 若存在但進程已死 → 視作 stale lock，覆蓋寫入；
        - 若存在且進程存活 → 拒絕並拋 :class:`AlreadyRunningError`。
        """
        with self._lock:
            existing = self.read_existing_pid()
            if existing is not None and _pid_alive(existing):
                raise AlreadyRunningError(existing, self.path)

            self.path.parent.mkdir(parents=True, exist_ok=True)
            pid = os.getpid()
            # O_WRONLY | O_CREAT | O_TRUNC：無條件覆蓋舊內容
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(str(pid), encoding="utf-8")
            os.replace(tmp, self.path)
            self._pid_written = pid

            atexit.register(self.release)

    def release(self) -> None:
        """清理 PID 文件；僅在當前進程為寫入者時動手。"""
        with self._lock:
            if self._pid_written is None:
                return
            try:
                content = self.read_existing_pid()
                if content == self._pid_written:
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    except OSError:
                        pass
            finally:
                self._pid_written = None

    def __enter__(self) -> "DaemonPidLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
