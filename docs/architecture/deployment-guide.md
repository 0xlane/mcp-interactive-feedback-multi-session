# 部署指南 · v3.0

> v3.0 是 **单实例 HTTP daemon**，需要用户显式把它跑起来并保持常驻。
> 所有 AI Agent（Cursor / Claude / Cline / 自制脚本）通过同一个
> `http://host:port/mcp/` 地址与它通信，不再每个 Agent 进程自带一个
> stdio 版本。
>
> **本仓库为自用分支，不发布到 PyPI**：安装方式只有「从源码运行」一种，
> 所有命令都基于 `git clone` + `uv sync` + `uv run`。

目录：

1. [前置条件](#1-前置条件)
2. [本地部署（源码运行）](#2-本地部署源码运行)
3. [SSH 远程 / 端口转发](#3-ssh-远程--端口转发)
4. [配置 AI Agent](#4-配置-ai-agent)
5. [进程管理 (launchctl / systemd / tmux)](#5-进程管理-launchctl--systemd--tmux)
6. [升级 / 回滚](#6-升级--回滚)
7. [卸载 / 清理](#7-卸载--清理)

---

## 1. 前置条件

- Python **3.11+**。
- `uv` ≥ 0.4（推荐最新）。安装：
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- 可写目录：
  - `~/.config/mcp-feedback-enhanced/`（ui_settings.json、
    session_history.json）
  - `~/.cache/uv/`（uv 下载缓存；参见
    [`../en/cache-management.md`](../en/cache-management.md) /
    [`zh-CN`](../zh-CN/cache-management.md) /
    [`zh-TW`](../zh-TW/cache-management.md)）
- 网络：
  - 本地使用无需公网；
  - SSH 远程场景需要能 SSH 到远程主机，能建立本地端口转发。

---

## 2. 本地部署（源码运行）

本仓库不发布 PyPI，所以部署 = clone + uv sync + uv run：

```bash
git clone https://github.com/0xlane/mcp-interactive-feedback-multi-session.git
cd mcp-interactive-feedback-multi-session
uv sync
uv run mcp-interactive-feedback serve --http
```

等价完整写法：

```bash
uv run mcp-interactive-feedback serve --http \
  --host 127.0.0.1 \
  --port 8765 \
  --log-level info
```

成功后终端会打印类似：

```
INFO: Uvicorn running on http://127.0.0.1:8765 (Press CTRL+C to quit)
```

然后浏览器打开：

```
http://127.0.0.1:8765
```

> 不想每条命令都带 `uv run`？`uv sync` 已生成 `.venv/`，执行一次
> `source .venv/bin/activate` 即可直接用 `mcp-interactive-feedback`。
> 如要一个全局命令，也可以 `uv tool install --from . mcp-interactive-feedback`
> 把当前源码装成工具。

### 2.1 常用参数速查

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--host` | `127.0.0.1` | 绑定地址。跨主机请改成 `0.0.0.0` 或内网 IP，并自觉加防火墙/端口转发 |
| `--port` | `8765` | 被占用**不会**自动递增，直接失败。固定端口有助于 `mcp.json` 稳定 |
| `--log-level` | `info` | `critical` / `error` / `warning` / `info` / `debug` / `trace` |

### 2.2 日志

`info` 级已经包含所有业务级事件；排查复杂问题时切到 `debug`。
终端日志不落盘；若要长时间保留，请配合 `tee`、`systemd` 或外置日志
管理工具。

---

## 3. SSH 远程 / 端口转发

详见 [`../en/ssh-remote/browser-launch-issues.md`](../en/ssh-remote/browser-launch-issues.md)
（含中英繁三语版本）。核心步骤：

1. 在**远程主机**启动 daemon（仓库需先 clone 到远程）：

   ```bash
   cd /path/to/mcp-interactive-feedback-multi-session
   uv run mcp-interactive-feedback serve --http --port 8765
   ```

2. 在**本地机器**建立 SSH 端口转发：

   ```bash
   ssh -N -L 8765:127.0.0.1:8765 user@remote-host
   ```

   也可以让 IDE 代办（VS Code / Cursor 的 Forwarded Ports 面板）。

3. 本地浏览器访问：

   ```
   http://127.0.0.1:8765
   ```

若远程 Agent 与 daemon 在**同一台远程主机**上，`mcp.json` 可以直接
配 `http://127.0.0.1:8765/mcp/`；从本地访问 UI 走上面的端口转发即可。

---

## 4. 配置 AI Agent

### 4.1 Cursor / Claude Desktop

在 `mcp.json` 里增加：

```json
{
  "mcpServers": {
    "mcp-feedback-enhanced": {
      "transport": "http",
      "url": "http://127.0.0.1:8765/mcp/",
      "headers": {}
    }
  }
}
```

- Cursor 中 `mcp.json` 通常在 `~/.cursor/mcp.json` 或项目 `.cursor/mcp.json`。
- `url` 结尾的 `/mcp/` **必须保留**，否则会命中 SPA 外壳 404。
- `headers` 留空即可；v3.0 未启用鉴权。

### 4.2 Cursor CLI / 其它 MCP 客户端

任何支持 Streamable HTTP 的 MCP 客户端都可以直接指向同一个 URL。
不同客户端之间互相感知：它们的 `interactive_feedback` 调用都落到
**同一个** daemon，用户在同一个浏览器里一次性处理。

### 4.3 推荐做法

- 给每个 Agent 调用 `interactive_feedback` 时都带上 `title`，让侧栏
  可以一眼分辨来源（例如 `"Cursor - 重构 hotkeys"`、
  `"CLI - 批量重命名脚本"`）。
- 同一台机器多开 Cursor 项目 + 多开终端 Cline 是典型场景，v3.0
  就是为此设计。

---

## 5. 进程管理 (launchctl / systemd / tmux)

v3.0 不内建「后台守护进程」模式：`uv run ... serve --http` 是前台阻塞
的。推荐用系统自带工具把它拉起来。

### 5.1 macOS · launchctl

`~/Library/LaunchAgents/com.user.mcp-feedback-enhanced.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.user.mcp-feedback-enhanced</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/you/.local/bin/uv</string>
    <string>run</string>
    <string>--directory</string>
    <string>/Users/you/path/to/mcp-interactive-feedback-multi-session</string>
    <string>mcp-interactive-feedback</string>
    <string>serve</string>
    <string>--http</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8765</string>
    <string>--log-level</string><string>info</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key>
  <string>/Users/you/Library/Logs/mcp-feedback-enhanced.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/you/Library/Logs/mcp-feedback-enhanced.err</string>
</dict>
</plist>
```

加载：

```bash
launchctl load -w ~/Library/LaunchAgents/com.user.mcp-feedback-enhanced.plist
```

### 5.2 Linux · systemd user unit

`~/.config/systemd/user/mcp-feedback-enhanced.service`：

```ini
[Unit]
Description=MCP Feedback Enhanced (HTTP daemon)
After=network-online.target

[Service]
WorkingDirectory=%h/path/to/mcp-interactive-feedback-multi-session
ExecStart=%h/.local/bin/uv run mcp-interactive-feedback serve --http --port 8765
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

启用：

```bash
systemctl --user daemon-reload
systemctl --user enable --now mcp-feedback-enhanced
journalctl --user -u mcp-feedback-enhanced -f
```

### 5.3 SSH 远程 · tmux / screen

懒人法：

```bash
ssh user@remote
tmux new -s mcp-fb
cd /path/to/mcp-interactive-feedback-multi-session
uv run mcp-interactive-feedback serve --http --port 8765
# Ctrl+B D detach，下次 tmux attach -t mcp-fb
```

### 5.4 Windows · 推荐 WSL

目前主要在 macOS / Linux 上测试。Windows 原生建议用 WSL2 + 上面的
systemd user unit；或自行包装 Task Scheduler。

---

## 6. 升级 / 回滚

### 6.1 升级

```bash
# 1. 停 daemon（Ctrl+C 或 launchctl unload / systemctl --user stop）
# 2. 更新源码 + 依赖
cd /path/to/mcp-interactive-feedback-multi-session
git pull
uv sync
# 3. 重新启动
uv run mcp-interactive-feedback serve --http
```

- 启动后可通过 `uv run mcp-interactive-feedback version` 或页脚查看版本号。
- 版本号管理：`make bump-patch` / `bump-minor` / `bump-major`（仅更新本地
  版本字符串，不会触发发布）。

### 6.2 固定版本

```bash
cd /path/to/mcp-interactive-feedback-multi-session
git checkout <tag-or-commit>
uv sync
uv run mcp-interactive-feedback serve --http
```

### 6.3 回滚

```bash
cd /path/to/mcp-interactive-feedback-multi-session
git checkout <previous-tag>
uv sync
uv run mcp-interactive-feedback serve --http
```

> ⚠️ 如要回滚到上游 v2.x 的 stdio 形态，直接使用上游仓库
> [Minidoracat/mcp-feedback-enhanced](https://github.com/Minidoracat/mcp-feedback-enhanced)
> 的对应版本；本 fork 不提供 stdio 兼容层，`mcp.json` 也要一并切回
> `command/args` 形态。

---

## 7. 卸载 / 清理

1. 停止 daemon（`Ctrl+C`、`launchctl unload` 或 `systemctl --user disable --now`）。
2. 删除源码目录：`rm -rf /path/to/mcp-interactive-feedback-multi-session`。
3. 清理 uv 缓存（可选）：`uv cache clean`。
4. 删除配置：`rm -rf ~/.config/mcp-feedback-enhanced`。
5. 若通过 `uv tool install` 装过全局命令：`uv tool uninstall mcp-interactive-feedback`。
6. 撤销 Agent 侧的 `mcp.json` 条目。

---

**文档版本**：v3.0.1 · **最后更新**：2026-04-24
