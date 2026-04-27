# 系统架构总览 · v3.0

> 本文档对应 v3.0（HTTP Daemon + 单实例多会话）。历史 v2.x
> （stdio + 每 agent 一实例 + 单活跃会话）架构不再是主线，仅在
> `phase2-http-daemon-usage.md` 的迁移说明与 `multi-session-http-redesign.md`
> 的「现状痛点」一节中回顾。
>
> 完整的设计背景、取舍和落地细节请参见
> [`multi-session-http-redesign.md`](./multi-session-http-redesign.md)。

---

## 1. 核心设计理念

v3.0 的目标非常聚焦：

1. **单一守护进程**：整台机器长期运行一个 `mcp-feedback-enhanced`
   守护（daemon），由用户手动 `uvx … serve --http` 启动。
2. **多会话并存**：每次 AI Agent 调用 `interactive_feedback` 都会创建
   一个 `WebFeedbackSession`，多个会话可在同一进程内并存，不再互相
   销毁。
3. **单浏览器视图**：所有反馈在**同一个浏览器页面**里查看、切换、
   归档；不再为每次调用重新开一个 tab。
4. **HTTP 传输为唯一协议**：MCP 以 Streamable HTTP 方式挂载在
   FastAPI 上，与 Web UI 共享一个端口；stdio 模式已移除。
5. **面向本地 / 端口转发**：默认绑定 `127.0.0.1`，无需鉴权；
   SSH 远程场景通过端口转发访问，见 `ssh-remote/` 指南。
6. **桌面模式暂停**：v3.0 聚焦 Web Only；Tauri 桌面相关代码仍保留在
   `src-tauri/` 作为参考，但本自用分支不再构建桌面 App。

---

## 2. 技术栈

**后端**

- Python 3.11+
- [FastMCP 2.x](https://gofastmcp.com/) —— 提供 MCP Streamable HTTP
  传输，挂载为 FastAPI sub-app
- [FastAPI](https://fastapi.tiangolo.com/) + uvicorn —— Web UI + 静态
  资源 + WebSocket
- 内建 `WebUIManager`（单例）管理会话字典、活跃指针、连接集合、广播

**前端**

- 原生 ES modules（`app.js` / `session-store.js` / `session-sidebar.js`
  / `websocket-manager.js` / `notify-badge.js` / …）
- Jinja2 模板 + 三语 i18n JSON
- Canvas 画 favicon 红点，`Notification` API 发系统通知，
  `Cmd/Ctrl+1..9` 切会话

**工具链**

- 包管理：`uv` / `uvx`
- 测试：`pytest` + `pytest-asyncio`
- 质量：`ruff` + `mypy`（基线），`pre-commit` 钩子

---

## 3. 进程与端口拓扑

```text
┌───────────────────────────────────────────────────────────────┐
│  Host (本地 or SSH remote)                                     │
│                                                               │
│   ┌─────────────────────────────────────┐                     │
│   │  uv run mcp-interactive-feedback    │  ← daemon 进程       │
│   │  --http [--host 127.0.0.1:0]        │                     │
│   │                                     │                     │
│   │  ┌──────────────────────────────┐   │                     │
│   │  │ FastAPI (uvicorn)            │   │                     │
│   │  │  ├─ /                (SPA)   │   │◄─── 用户浏览器      │
│   │  │  ├─ /api/sessions            │   │                     │
│   │  │  ├─ /ws  (multiplex)         │   │                     │
│   │  │  └─ /mcp (FastMCP HTTP)      │   │◄─── AI Agent #1     │
│   │  └──────────────────────────────┘   │                     │
│   │                                     │◄─── AI Agent #2     │
│   │  WebUIManager (内存)                 │◄─── AI Agent #N     │
│   │   ├─ sessions: {sid → session}       │                     │
│   │   ├─ connections: {ws, ws, …}        │                     │
│   │   └─ _active_session_id (粘滞)        │                     │
│   └─────────────────────────────────────┘                     │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

- **端口**：默认 `--port 8765`；也可显式指定。端口被占用时直接失败（不
  做自动递增）。
- **连接聚合**：多个 Agent 通过 `/mcp` 发起调用，多个浏览器 tab 通过
  `/ws` 订阅同一批事件；WS 是多路复用的单通道，靠 `session_id` 在消
  息体里路由。

---

## 4. 四层架构（v3.0）

```
┌─────────────────────────────────────────────────────────────┐
│ 第 1 层：MCP 服务层                                          │
│   server.py          → interactive_feedback(summary,title,  │
│                          timeout) 工具实现                   │
│   FastMCP (http_app) → 以 ASGI sub-app 挂在 /mcp            │
│   i18n.py / debug.py → 日志与多语言                          │
├─────────────────────────────────────────────────────────────┤
│ 第 2 层：会话管理层                                          │
│   WebUIManager       → 单例，进程级会话字典、活跃指针、      │
│                          WS 连接集合、广播总线               │
│   WebFeedbackSession → 单个会话的状态机                      │
│   SessionStatus      → WAITING/FEEDBACK_SUBMITTED/           │
│                          COMPLETED/ERROR/TIMEOUT/EXPIRED/   │
│                          CANCELED                           │
├─────────────────────────────────────────────────────────────┤
│ 第 3 层：Web 服务层                                          │
│   FastAPI app (web/main.py)                                 │
│   routes/main_routes.py  → HTML、/api/sessions、/ws          │
│   routes/image_routes.py → 图片上传                          │
│   templates/feedback.html (SPA 外壳)                         │
├─────────────────────────────────────────────────────────────┤
│ 第 4 层：前端层                                              │
│   app.js (入口)                                             │
│   session-store.js / session-sidebar.js (侧栏 + 状态)       │
│   websocket-manager.js (多路复用 WS 客户端)                  │
│   notify-badge.js      (title(N)、favicon 红点、系统通知、    │
│                          Cmd/Ctrl+1..9 快捷键)               │
│   ui-manager.js / image-handler.js / settings-manager.js    │
└─────────────────────────────────────────────────────────────┘
```

详细模块责任见 [`component-details.md`](./component-details.md)；
消息/接口形态见 [`api-reference.md`](./api-reference.md)。

---

## 5. 典型调用序列（摘要）

```
AI Agent                 FastAPI /mcp          WebUIManager         Browser
   │                        │                        │                 │
   │ interactive_feedback   │                        │                 │
   ├───────────────────────►│                        │                 │
   │                        │ create_session(...)    │                 │
   │                        ├───────────────────────►│                 │
   │                        │                        │  broadcast      │
   │                        │                        │  session_created│
   │                        │                        ├────────────────►│
   │                        │                        │                 │ (侧栏新增卡片)
   │                        │ wait_for_feedback(sid) │                 │
   │                        ├───────────────────────►│                 │
   │                        │                        │  submit_feedback│
   │                        │                        │◄────────────────┤
   │                        │  feedback payload      │                 │
   │◄───────────────────────┤◄───────────────────────┤                 │
```

完整的流程图（含首次启动、切换会话、归档、超时等）见
[`interaction-flows.md`](./interaction-flows.md)。

---

## 6. 粘滞活跃指针（Sticky Active Pointer）

v3.0 里 `_active_session_id` 是「**前端当前正在看哪个会话**」的真源。

- 用户打开浏览器、点击侧栏卡片、按 `Cmd+1..9` 时，前端通过 WS
  `set_active_session` 通知后端同步指针。
- 新的 `create_session` 不会强行抢占这个指针：只有在「当前没有活跃
  会话」或「指针指向一个已不存在的会话」时才把新会话设为活跃。
- 这样一来，用户在看 Session A 的时候，Agent 新建的 Session B **不会**
  把界面切走；B 以「pending」状态出现在侧栏，title 上加 `(N)` 计数，
  favicon 打红点。

背后的 bug 史（`launch_web_feedback_ui` 旧版用 `get_current_session()`
导致串线）和修复方案记录在
[`multi-session-http-redesign.md`](./multi-session-http-redesign.md) §8
「Phase 3 实际落地差异与经验教训」一节。

---

## 7. 会话生命周期（摘要）

```
           create_session
   ──────────────────────►   WAITING
                                │
          第一条反馈表单提交     │
                                ▼
                          FEEDBACK_SUBMITTED
                                │
                 wait_for_feedback 返回结果
                                ▼
                           COMPLETED
                                │
                前端「清除」(archive) / 超时到期
                                ▼
                (从 sessions 字典中物理移除)
```

其他状态：

- `TIMEOUT`：`wait_for_feedback` 到 `timeout` 参数时限。
- `EXPIRED`：超出保留期（例如 1 小时空闲）被清理。
- `ERROR` / `CANCELED`：异常或主动取消。

归档是「物理删除」：会话对象从 `self.sessions` 中 `pop` 掉，
`_session_creation_order` 同步清除。这样即便前端刷新，也**不会**把
已归档的会话重新拉回来。

---

## 8. 与 v2.x 的差异一览

| 维度 | v2.x（历史） | v3.0（当前） |
| --- | --- | --- |
| 传输 | stdio | Streamable HTTP |
| 进程模型 | 每个 AI Agent 起一个独立实例 | 机器级单守护 |
| 并发会话 | 1 个（新会话销毁旧会话） | 多会话并存 |
| 浏览器 tab | 每次 MCP 调用新开 | 始终复用同一个 SPA 页面 |
| 端口 | 自动端口 + 短期 | 固定/指定端口 + 常驻 |
| 桌面模式 | Tauri 构建线 | 暂停（代码仍在，CI 已禁） |
| 鉴权 | 无 | 无（本地回环为主） |
| 老的 `index.html` 等待页 | 有 | 已删除，根路由即 SPA |

---

## 9. 阅读路径建议

| 你是谁 / 想干嘛 | 先读 |
| --- | --- |
| 用户想把 daemon 跑起来 | [`phase2-http-daemon-usage.md`](./phase2-http-daemon-usage.md) |
| 用户想理解界面、快捷键、归档 | [`phase3-multi-session-ui-usage.md`](./phase3-multi-session-ui-usage.md) |
| 开发想动后端模块 | `component-details.md` + `multi-session-http-redesign.md` |
| 想对接 REST/WS 接口 | [`api-reference.md`](./api-reference.md) |
| 想部署（本地、SSH 远程） | [`deployment-guide.md`](./deployment-guide.md) |

---

**文档版本**：v3.0.0-dev · **最后更新**：2026-04-22
