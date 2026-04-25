# SSH Remote 使用指南（v3.0 HTTP Daemon 模式）

> 已更新至 v3.0。旧的「等 MCP 自动打开浏览器」流程已废弃——v3.0 改为
> 在远端跑一个常驻 daemon，你用**本地**浏览器通过 SSH 端口转发连进去。

## v3.0 模型变化

v2.x 每次 `interactive_feedback` 调用都会在 MCP 服务器所在主机上尝试
打开浏览器。SSH Remote（VS Code Remote / Cursor Remote / 等）远端
没有显示环境，所以会报错失败。

v3.0 反转了这个模型：

- 在远端启动**一个** daemon：`serve --http`；
- daemon 自己不再打开浏览器，只监听端口；
- 你从**本地**浏览器通过 SSH 转发的端口连进去（例如 `http://localhost:8765/`）；
- 所有 AI agent（Cursor Chat 等）向同一个 daemon URL 发 MCP 调用。

## 1. 在远端启动 daemon

根据你想用哪种转发方式，绑定选项有两种：

### 方案 A —— 绑定 localhost，用 SSH 转发（推荐）

远端执行：

```bash
# 前台运行，Ctrl+C 停止（在 clone 的仓库目录中执行）
uv run mcp-interactive-feedback serve --http
# 或
uv run python -m mcp_feedback_enhanced serve --http
```

默认绑定 `127.0.0.1:8765`，仅本机可访问，远端网络看不到。

然后在本地做端口转发（见 §2）。

### 方案 B —— 绑定所有网卡（仅在你控制网络时使用）

```bash
uv run mcp-interactive-feedback serve --http --host 0.0.0.0 --port 8765
```

会在所有网卡监听。**仅当**远端在防火墙后且端口不对公网开放时安全。
daemon 本身不做鉴权。

## 2. 本地端口转发

### VS Code Remote SSH

1. `Ctrl/Cmd+Shift+P` → `Forward a Port`；
2. 输入 `8765`；
3. 本地浏览器打开 `http://localhost:8765/`。

![端口设置](../images/ssh-remote-port-setting.png)
![连接 URL](../images/ssh-remote-connect-url.png)

### Cursor Remote

1. 打开 Ports 面板（命令面板 → `Toggle Ports`）；
2. 添加 `8765` 的转发规则；
3. 本地访问 `http://localhost:8765/`。

### 纯 SSH 命令行

```bash
ssh -L 8765:127.0.0.1:8765 user@remote-host
# 然后本地浏览器：http://localhost:8765/
```

## 3. Agent 端 `mcp.json`

你的 AI agent（Cursor IDE）跑在**本地**，只要本地能访问 MCP 端点就行。
SSH 转发之后：

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

URL 末尾 `/` 必须保留。

## 4. 首次可用性测试

```bash
# 在本地笔记本上，SSH 转发起来之后
curl http://localhost:8765/api/all-sessions
# → {"sessions":[]}
curl -s http://localhost:8765/ | head -n 5
# → HTML
```

两条都通后，在 Cursor 里发一条会触发 `interactive_feedback` 的消息。
`http://localhost:8765/` 的侧栏应出现新卡片。

## 5. 常见问题

**Q：还需要设置 `MCP_WEB_HOST=0.0.0.0` 吗？**
A：不需要。那是 v2.x 为解决"远端自动打开的浏览器看不到本地"临时
搞的环境变量。v3.0 如果真要绑所有网卡，直接 `serve --host 0.0.0.0`
（方案 B）。

**Q：daemon 报 `address already in use`。**
A：其他 `mcp-feedback-enhanced` 进程或别的服务占着 8765。要么停
（`lsof -i :8765` → 杀 PID），要么 `--port 18765` 换端口并同步改
SSH 转发。

**Q：agent 一直连本地 8765，但 daemon 在服务器上——没反应。**
A：SSH 端口转发其实没生效。回到 §2 重新检查，先用
`curl http://localhost:8765/api/all-sessions` 从笔记本验证能通，再
发起 AI 调用。

**Q：SSH 断开后 daemon 还能活着吗？**
A：直接 `uv run ... serve --http` 前台进程，Ctrl+C / SIGHUP 会把它杀掉。
要长期存活用 `tmux` / `screen` / `nohup`：

```bash
tmux new -d -s mcp-feedback 'uv run mcp-interactive-feedback serve --http'
```

v3.0 刻意不提供 LaunchAgent / systemd 模板（设计决议见
[multi-session-http-redesign.md §7.14](../../architecture/multi-session-http-redesign.md)）。

**Q：同一台远端机上能否多个用户共用一个 daemon？**
A：不推荐。会话列表会在所有访问者之间共享——隐私风险。每人起自己的
daemon，分配不同端口。

**Q：浏览器 console 偶尔显示 WebSocket "disconnected"（网络抖动之后）。**
A：页面会自动重连。若没有，刷新即可——会话状态全部在服务端，
`sessions_snapshot` 事件会重新同步。

---

**相关文档**：
- [阶段 2：HTTP Daemon 使用指南](../../architecture/phase2-http-daemon-usage.md)
- [阶段 3：双栏多会话 UI 使用指南](../../architecture/phase3-multi-session-ui-usage.md)
- [Cache 管理](../cache-management.md)
