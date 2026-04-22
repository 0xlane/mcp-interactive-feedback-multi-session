"""
DaemonPidLock 單元測試
====================

驗證：
- 首次 acquire 寫入 PID、返回當前進程
- 第二次 acquire（同一進程）應 raise AlreadyRunningError
- stale lock（PID 指向不存在的進程）自動回收
- release 清理文件
- 上下文管理器語法正常
- `default_pid_path` 尊重 `MCP_FEEDBACK_PID_FILE` 環境變數
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcp_feedback_enhanced.utils import pid_lock as pid_lock_module
from mcp_feedback_enhanced.utils.pid_lock import (
    AlreadyRunningError,
    DaemonPidLock,
    default_pid_path,
)


def test_default_pid_path_env_override(tmp_path, monkeypatch):
    """MCP_FEEDBACK_PID_FILE 應完全覆蓋默認邏輯。"""
    custom = tmp_path / "daemon.pid"
    monkeypatch.setenv("MCP_FEEDBACK_PID_FILE", str(custom))
    assert default_pid_path() == custom


def test_default_pid_path_xdg_config_home(tmp_path, monkeypatch):
    """未設 MCP_FEEDBACK_PID_FILE 時，應使用 XDG_CONFIG_HOME。"""
    monkeypatch.delenv("MCP_FEEDBACK_PID_FILE", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    import sys

    if sys.platform == "win32":
        pytest.skip("XDG_CONFIG_HOME does not apply on win32 path")
    expected = tmp_path / "mcp-feedback-enhanced" / "daemon.pid"
    assert default_pid_path() == expected


def test_acquire_writes_pid_and_release_cleans(tmp_path):
    pid_file = tmp_path / "daemon.pid"
    lock = DaemonPidLock(pid_file)

    lock.acquire()
    try:
        assert pid_file.exists()
        assert pid_file.read_text(encoding="utf-8").strip() == str(os.getpid())
    finally:
        lock.release()

    assert not pid_file.exists()


def test_double_acquire_from_same_process_raises(tmp_path):
    """第二把鎖看到同 PID 存活，應拒絕。"""
    pid_file = tmp_path / "daemon.pid"
    first = DaemonPidLock(pid_file)
    first.acquire()
    try:
        second = DaemonPidLock(pid_file)
        with pytest.raises(AlreadyRunningError) as excinfo:
            second.acquire()
        assert excinfo.value.pid == os.getpid()
        assert excinfo.value.path == pid_file
    finally:
        first.release()


def test_stale_lock_is_reclaimed(tmp_path, monkeypatch):
    """PID 文件內容指向已死進程時，應覆蓋並繼續。"""
    pid_file = tmp_path / "daemon.pid"
    pid_file.write_text("999999999", encoding="utf-8")

    monkeypatch.setattr(pid_lock_module, "_pid_alive", lambda pid: False)

    lock = DaemonPidLock(pid_file)
    lock.acquire()
    try:
        assert pid_file.read_text(encoding="utf-8").strip() == str(os.getpid())
    finally:
        lock.release()


def test_foreign_alive_process_is_rejected(tmp_path, monkeypatch):
    """PID 文件對應的進程仍存活時，應拒絕並保留原內容。"""
    pid_file = tmp_path / "daemon.pid"
    pid_file.write_text("123456", encoding="utf-8")

    monkeypatch.setattr(pid_lock_module, "_pid_alive", lambda pid: True)

    lock = DaemonPidLock(pid_file)
    with pytest.raises(AlreadyRunningError) as excinfo:
        lock.acquire()
    assert excinfo.value.pid == 123456
    assert pid_file.read_text(encoding="utf-8").strip() == "123456"


def test_release_without_acquire_is_noop(tmp_path):
    pid_file = tmp_path / "daemon.pid"
    lock = DaemonPidLock(pid_file)
    lock.release()
    assert not pid_file.exists()


def test_context_manager(tmp_path):
    pid_file = tmp_path / "daemon.pid"
    with DaemonPidLock(pid_file) as lock:
        assert pid_file.exists()
        assert pid_file.read_text(encoding="utf-8").strip() == str(os.getpid())
        assert isinstance(lock, DaemonPidLock)
    assert not pid_file.exists()


def test_release_does_not_delete_foreign_pid_file(tmp_path):
    """若 release 執行時文件內容已被其他進程接管，不應誤刪。"""
    pid_file = tmp_path / "daemon.pid"
    lock = DaemonPidLock(pid_file)
    lock.acquire()
    pid_file.write_text("987654", encoding="utf-8")
    lock.release()
    assert pid_file.exists()
    assert pid_file.read_text(encoding="utf-8").strip() == "987654"
    pid_file.unlink()  # 清理測試殘留


def test_read_existing_pid_returns_none_when_missing(tmp_path):
    lock = DaemonPidLock(tmp_path / "no_such.pid")
    assert lock.read_existing_pid() is None


def test_read_existing_pid_returns_none_when_malformed(tmp_path):
    pid_file = tmp_path / "daemon.pid"
    pid_file.write_text("not-a-pid", encoding="utf-8")
    lock = DaemonPidLock(pid_file)
    assert lock.read_existing_pid() is None


def test_parent_directory_is_created(tmp_path):
    """acquire 應自動建立父目錄。"""
    pid_file = tmp_path / "deep" / "nested" / "daemon.pid"
    lock = DaemonPidLock(pid_file)
    lock.acquire()
    try:
        assert pid_file.exists()
    finally:
        lock.release()
