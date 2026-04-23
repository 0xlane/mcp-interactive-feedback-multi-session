# 阶段 2：HTTP 单实例 Daemon 使用指南

> **状态**：阶段 2 已落地，本文档给出开发者 / 早期用户可立即使用的最小上手路径。
> **面向对象**：Cursor IDE、Cursor CLI 用户，以及希望在本地手动验证 HTTP 模式的开发者。
> 正式 README（三语）将在阶段 5 完成后统一覆盖；此文件用作阶段性过渡。

## 1. 启动 Daemon

Daemon 必须由用户手动启动，进程常驻，服务同一用户下所有 AI Agent。

```bash
# 前台启动（Ctrl+C 结束）
uvx mcp-feedback-enhanced serve --http

# 或使用已 clone 的源码
uv run python -m mcp_feedback_enhanced serve --http
```

### 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--http` | - | 标记 HTTP 模式；当前 `serve` 仅支持 HTTP，保留此旗标便于未来扩展 |
| `--host` | `127.0.0.1` | 绑定主机，**强烈建议保持默认**（本地单用户场景，不做鉴权） |
| `--port` | `8765` | 绑定端口；被占用直接报错退出，不做自动递增 |
| `--log-level` | `info` | uvicorn 日志级别 |
| `--pid-file` | `~/.config/mcp-feedback-enhanced/daemon.pid` | PID 文件路径 |

### PID 冲突

- 同用户下只允许一个 Daemon 运行；第二次启动会报：
  ```
  ✗ mcp-interactive-feedback daemon already running (pid=NNNN, pidfile=...)
    提示：若确认前一个 daemon 已死，可手动删除 PID 文件后重试。
  ```
- 正常退出（Ctrl+C / `kill <pid>`）会自动清理 PID 文件；异常退出遗留的 PID 文件会在下次启动时被识别为 stale lock 并回收（前提：PID 对应的进程已死）。

## 2. 配置 `mcp.json`

**阶段 2 的 `mcp.json` 应切换为 HTTP transport**，不再 fork stdio 子进程。

### Cursor IDE / Cursor CLI

`~/.cursor/mcp.json`（或项目内 `.cursor/mcp.json`）：

```json
{
  "mcpServers": {
    "mcp-feedback-enhanced": {
      "url": "http://127.0.0.1:8765/mcp/",
      "autoApprove": ["interactive_feedback"]
    }
  }
}
```

要点：
- 尾部 `/` 必须保留，`/mcp/` 是 Streamable HTTP 端点；
- 不需要 `command` / `args` / `env` —— AI Agent 直接走 HTTP；
- `timeout` 字段对 HTTP transport 无效（由 MCP 协议自身处理）。

### 向下兼容（过渡期）

`server`（stdio）子命令仍保留，但不再推荐使用：

```bash
# ⚠️ 过渡保留，阶段 5 将移除
uvx mcp-feedback-enhanced server
```

## 3. 端点一览

Daemon 启动后对外开放：

| 路径 | 协议 | 用途 |
|---|---|---|
| `GET /` | HTTP | Web UI 主页（用户在浏览器里打开） |
| `GET /api/all-sessions` | HTTP | 全量会话列表（含 `title`、`status`） |
| `POST /api/sessions/{id}/archive` | HTTP | 手动归档会话（阶段 1 已上线） |
| `GET /ws` | WebSocket | 前端推送通道 |
| `POST /mcp/` | HTTP (SSE) | AI Agent 调用 MCP 工具的端点 |

## 4. 首次上手流程

1. 终端 A：`uvx mcp-feedback-enhanced serve --http` —— daemon 启动；
2. 浏览器打开 `http://127.0.0.1:8765/` —— Web UI；
3. 修改 `~/.cursor/mcp.json` 如上；
4. 在 Cursor 发起一次 `interactive_feedback` 调用 —— 会话出现在浏览器里；
5. 再起第二个 Chat 并发调用 —— 会话被追加到同一个浏览器页面。
   > ✅ 阶段 3 落地后，新会话不再挤掉旧会话显示：侧栏列出全部并行
   > 会话，你保持在当前会话里不被打断，新会话通过红点 + `(N)` 标题
   > 前缀 + 桌面通知提示。详见
   > [phase3-multi-session-ui-usage.md](./phase3-multi-session-ui-usage.md)。

## 5. 常见问题

**Q：启动报 `daemon already running`**
A：先检查 `lsof -i :8765` 或 `ps | grep mcp_feedback_enhanced`。若进程已死仅残留 PID 文件，直接删除 `~/.config/mcp-feedback-enhanced/daemon.pid` 后重试即可。

**Q：MCP 工具返回 404**
A：确认 `mcp.json` 的 `url` 字段尾部有 `/`。访问 `/mcp`（无尾斜线）会被 307 重定向到 `/mcp/`，大部分 MCP 客户端会自动跟随。

**Q：如何测试 daemon 是否健康**
A：
```bash
curl http://127.0.0.1:8765/api/all-sessions           # 应返回 {"sessions":[...]}
curl -s http://127.0.0.1:8765/                        # 应返回 Web UI HTML
```

**Q：想绑别的端口**
A：`uvx mcp-feedback-enhanced serve --http --port 18765`，同步改 `mcp.json` 的 `url` 即可。不做自动递增是为了让 `mcp.json` 里的 URL 稳定可复制。

## 6. 已知限制（阶段 2）

> ✅ 表示阶段 3 已解决，仍属于阶段 2 文档范畴的限制以原文保留。

- ~~Web UI 视觉层仍为「单活跃会话」，多会话的侧栏切换体验在阶段 3 交付~~；
  ✅ 阶段 3 已交付雙栏 UI，参见
  [phase3-multi-session-ui-usage.md](./phase3-multi-session-ui-usage.md)。
- ~~归档仅能通过 `POST /api/sessions/{id}/archive` API 调用，尚无前端按钮（阶段 4）~~；
  ✅ 阶段 3 已在侧栏卡片右上角提供 `[X]` 归档按钮 + 批量「清除已完成」
  按钮（底层仍可走 REST API，方便自动化脚本）。
- 不提供 LaunchAgent / systemd 模板，需用户自行管理前台进程；
- Tauri 桌面模式暂停维护，仅支持浏览器。
