# API 参考 · v3.0

> 本页列出 v3.0 daemon 对外暴露的所有接口：MCP 工具、REST、WebSocket。
> 字段摘自 `src/mcp_feedback_enhanced/web/` 源码；若与实现不一致以代
> 码为准，发现问题请顺手在此更新。

---

## 目录

1. [MCP 工具](#1-mcp-工具)
2. [REST 接口](#2-rest-接口)
3. [WebSocket 接口](#3-websocket-接口)
4. [会话摘要对象](#4-会话摘要对象)
5. [错误约定](#5-错误约定)

---

## 1. MCP 工具

Daemon 启动后，FastMCP 将以 Streamable HTTP 传输挂在 `/mcp/`。Agent 端
（Cursor / Claude / 其它 MCP 客户端）在 `mcp.json` 中配置：

```jsonc
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

### 1.1 `interactive_feedback`

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `project_directory` | `string` | *必填* | Agent 正在工作的项目根路径，仅用于 UI 展示 / 关联 |
| `summary` | `string` | *必填* | 本次反馈的上下文/问题描述；会直接渲染到 UI |
| `timeout` | `int` | `600` | 最长等待反馈秒数；到时 `wait_for_feedback` 抛 `TimeoutError`，UI 上该会话转 `TIMEOUT` |
| `title` | `string?` | `None` | 会话标题；强烈建议填写，侧栏/标题栏/快捷键都靠它识别 |
| `feedback_session_id` | `string?` | `None` | 上一轮工具返回中的 session ID；传入后同一对话的多轮反馈复用同一个前端会话 |

返回值：`list[TextContent | ImageContent]`，内容依次是：

1. 一段可读的 summary 文本（包含用户提交的自由文本、操作日志）；
2. 零到多个 `ImageContent`（PNG/JPEG，mimetype 透出）；
3. 一段 `TextContent`，格式为 `[feedback_session_id=<UUID>]`，供下轮调用传回以复用 session。

失败/取消情形：

- 超时：返回一条 `TextContent`，标注「会话已超时」并附任何已累积的
  用户消息；
- 用户手动归档：返回 `TextContent`，内容是「用户取消了本次反馈」；
- 服务端异常：抛 `RuntimeError`，由 FastMCP 转成 tool error 返回给
  Agent。

---

## 2. REST 接口

所有路径均相对于 daemon 的 HTTP 基址（默认 `http://127.0.0.1:8765`）。
除非特别说明，内容类型均为 `application/json; charset=utf-8`。

### 2.1 页面

| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/` | GET | 返回 SPA 外壳 HTML（`feedback.html`） |
| `/static/*` | GET | 静态资源（JS/CSS/字体/图片） |

### 2.2 会话

#### `GET /api/sessions` ★ 多会话 UI 主数据源

响应：

```json
{
  "active_session_id": "b4a7...-c62",
  "connected_clients": 1,
  "sessions": [
    { /* 见 §4 会话摘要对象 */ }
  ]
}
```

- `sessions` 按 `created_at DESC`（同毫秒用 `_seq` 做 tie-breaker）。
- `connected_clients` = 当前 `/ws` 连接数。

#### `DELETE /api/sessions?status=<value>`

批量删除指定**终态**会话。

- `status` 可选值：`completed`、`timeout`、`expired`、`canceled`、
  `error`、以及特殊值 `all_terminal`（= 以上全部）。
- 不能用来删除 `WAITING` / `ACTIVE` / `FEEDBACK_SUBMITTED`，请改用
  `POST /api/sessions/{id}/archive`。
- 响应：

  ```json
  { "status": "success", "removed": ["sid1", "sid2"], "count": 2 }
  ```

#### `POST /api/sessions/{session_id}/archive`

手动归档单个会话（对应 UI 上的「清除」按钮）。

- Body（可选）：`{ "reason": "手动归档原因" }`
- 对 `WAITING` / `ACTIVE` 会话：调用 `session.cancel()` 解锁
  `wait_for_feedback`，对应 MCP 调用返回「用户取消」。
- 对 `FEEDBACK_SUBMITTED` / 终态会话：仅做 UI 归档（物理移除）。
- 若归档的是当前活跃会话，活跃指针会被 `_select_fallback_active_session`
  转移。
- 成功响应：

  ```json
  {
    "status": "success",
    "session_id": "...",
    "previous_status": "waiting",
    "current_status": "canceled"
  }
  ```

#### `POST /api/add-user-message`

向当前活跃会话追加一条补充消息（如用户在 UI 侧附加的提示）。

- 请求体：任意 JSON，推荐 `{ "message": "...", "timestamp": 0 }`。
- 没有活跃会话时返回 `404`。

#### 兼容接口（沿用 v2.x）

| 路径 | 方法 | 备注 |
| --- | --- | --- |
| `/api/session/status` | GET | 当前活跃会话状态摘要 |
| `/api/current-session` | GET | 当前活跃会话详情 |
| `/api/all-sessions` | GET | 全部会话详情（含 `has_websocket` 字段；`/api/sessions` 更推荐） |
| `/api/translations` | GET | i18n JSON；由前端加载 |

### 2.3 设置 / 历史 / 日志

| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/save-settings` | POST | 保存前端 UI 设置到 `~/.config/mcp-feedback-enhanced/ui_settings.json` |
| `/api/load-settings` | GET | 读取上述设置 |
| `/api/clear-settings` | POST | 清空设置文件 |
| `/api/load-session-history` | GET | 会话历史读 |
| `/api/save-session-history` | POST | 会话历史写 |
| `/api/log-level` | GET | 当前日志级别 |
| `/api/log-level` | POST | 设置日志级别（body: `{ "level": "debug" }`） |

### 2.4 MCP Streamable HTTP

| 路径 | 说明 |
| --- | --- |
| `/mcp/` | FastMCP 挂载的 Streamable HTTP 入口。由 FastMCP 自行处理 JSON-RPC 协议，外部请按官方客户端访问，不要直接手写。 |

---

## 3. WebSocket 接口

单一端点 `GET /ws?lang=zh-TW`（`lang` 可选，影响初始消息的文案）。
一条 `/ws` 对应一个浏览器 tab。多会话事件通过消息体里的 `session_id`
字段路由。

### 3.1 连接建立后服务端会发送

```jsonc
// 1) 首帧：连接建立确认（沿用旧协议）
{ "type": "connection_established", "messageCode": "websocket_connected" }

// 2) 全量会话快照（v3.0 新增）
{
  "type": "sessions_snapshot",
  "sessions": [ /* §4 会话摘要对象 */ ],
  "active_session_id": "...|null"
}

// 3) 视情况补发
//   - 若存在 _pending_session_update：一条 {type:"session_updated", action:"new_session_created"}
//   - 若存在当前活跃会话：一条 {type:"status_update", session_id, status_info}
```

### 3.2 客户端 → 服务端

所有消息均为 JSON，必填 `type`。除 `heartbeat` / `pong` /
`get_sessions_snapshot` / `set_active_session` 外，强烈建议带 `session_id`
明确目标；否则会回退到 `get_current_session()` 的**旧单会话**语义。

| `type` | 额外字段 | 作用 |
| --- | --- | --- |
| `heartbeat` | `timestamp` | 心跳；会被回 `heartbeat_response` |
| `pong` | `timestamp` | 服务端 ping 的回应（当前 v3.0 未主动 ping，保留） |
| `get_sessions_snapshot` | — | 前端怀疑漂移时主动要一次 `sessions_snapshot` |
| `set_active_session` | `session_id` | 通知后端同步 `_active_session_id`；回 `active_session_ack` |
| `submit_feedback` | `session_id`, `feedback`, `images`, `settings` | 提交本次反馈；`images` 为 `[{ name, type, data(base64) }]` |
| `run_command` | `session_id`, `command` | 执行简单的本地命令（v3.0 保留） |
| `get_status` | `session_id` | 主动拉一次 `status_update` |
| `archive_session` / `cancel_session` | `session_id`, `reason?` | 归档会话；回 `session_archive_ack`，并广播 `session_archived` |
| `user_timeout` | `session_id` | 前端宣告用户侧超时；触发清理 |
| `update_timeout_settings` | `session_id`, `settings:{enabled, seconds}` | 更新某会话的超时设置 |

### 3.3 服务端 → 客户端广播

统一结构 `{ type, session_id?, data... }`（会话相关的一定带 `session_id`）。

| `type` | 字段 | 说明 |
| --- | --- | --- |
| `sessions_snapshot` | `sessions`, `active_session_id` | 全量；连接首帧或客户端主动请求 |
| `session_created` | `session_id`, `summary`, `title`, `status`, `created_at`, `has_pending_notification`* | 新会话到来；`has_pending_notification` 由 websocket-manager 根据是否已有活跃会话决定 |
| `session_updated` | `session_id`, `status`, `status_message`, `title`, `last_activity` | 状态/元数据变更 |
| `session_removed` | `session_id` | 会话从字典中被删除（归档/清理） |
| `session_archived` | `session_id`, `previous_status`, `reason`, `status`, `status_message` | `archive_session` 语义的语义增强版（前端判断是否弹 toast） |
| `feedback_received` | `session_id` | 用户提交成功；前端清草稿 / 切只读 |
| `active_session_ack` | `session_id` | 服务端接受了 `set_active_session` |
| `session_archive_ack` | `session_id`, `ok`, `previous_status`, `current_status` | 发起归档的客户端专属回执 |
| `status_update` | `session_id`, `status_info` | 兼容旧前端 |
| `server_shutdown` | — | daemon 关停通告 |
| `error` | `session_id?`, `error_code`, `message` | 路由失败 / 消息异常 |

> 注：`session_created` 中 `has_pending_notification` 是前端规则，不一
> 定由后端设置；后端只保证广播到达，是否转成红点/系统通知由前端
> `websocket-manager.js` + `notify-badge.js` 决定。

### 3.4 典型消息示例

```jsonc
// 切会话：前端 → 后端
{ "type": "set_active_session", "session_id": "b4a7...-c62" }

// 后端 ack
{ "type": "active_session_ack", "session_id": "b4a7...-c62" }

// 提交反馈：前端 → 后端
{
  "type": "submit_feedback",
  "session_id": "b4a7...-c62",
  "feedback": "按钮颜色再亮一点",
  "images": [
    { "name": "screenshot.png", "type": "image/png", "data": "iVBORw0KGgo..." }
  ],
  "settings": { "tone": "concise" }
}

// 后端广播（所有连接）
{ "type": "feedback_received", "session_id": "b4a7...-c62" }
{
  "type": "session_updated",
  "session_id": "b4a7...-c62",
  "status": "feedback_submitted",
  "status_message": "使用者已提交反饋",
  "title": "重构侧栏样式",
  "last_activity": 1745340000000
}
```

---

## 4. 会话摘要对象

`sessions_snapshot` / `/api/sessions` / `/api/all-sessions` 用的统一形态：

```ts
type SessionSnapshot = {
  session_id: string;
  project_directory: string;
  summary: string;
  title: string | null;
  status:
    | "waiting"
    | "active"
    | "feedback_submitted"
    | "completed"
    | "error"
    | "timeout"
    | "expired"
    | "canceled";
  status_message: string;
  created_at: number;       // 毫秒
  last_activity: number;    // 毫秒
  feedback_completed: boolean;
  is_current: boolean;      // == (session_id === active_session_id)
  user_messages: Array<{ message: string; timestamp: number; /* ... */ }>;
};
```

`/api/all-sessions` 在此基础上额外返回 `has_websocket`（旧字段，指该
session 曾经绑过哪条 WS，用于兼容）。

---

## 5. 错误约定

- HTTP REST：
  - `400`：参数缺失/非法（`missing 'status' query parameter`、
    `invalid status: xxx`、`status '<x>' is not terminal`）。
  - `404`：资源不存在（`Session not found`、`No active session`）。
  - `500`：服务端异常，`error` 字段含原始信息，`messageCode` 指向
    i18n key（`get_sessions_failed` 等）。
- WebSocket：
  - 路由失败 → `{ type: "error", session_id?, error_code, message }`；
    `error_code` 目前有 `session_not_found` 一种；
  - 协议错误（JSON 解析失败、消息异常）会被日志记录，但不会断开
    已建立的连接；客户端需要容忍并在必要时重连；
  - WS 重连后**一定**会重发 `sessions_snapshot`，客户端应据此重建
    本地状态。

---

**文档版本**：v3.0.0-dev · **最后更新**：2026-04-22
