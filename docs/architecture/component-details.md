# 组件详细设计 · v3.0

> 本文档列出 v3.0 主要模块的职责、公共接口、关键协作关系，给后端 /
> 前端开发者快速定位实现位置。与 v2.x 的差异请对照
> [`multi-session-http-redesign.md`](./multi-session-http-redesign.md) §4
> 「影响矩阵」。

## 目录

1. [CLI 入口 (`__main__.py`)](#1-cli-入口-__main__py)
2. [HTTP Daemon (`daemon.py`)](#2-http-daemon-daemonpy)
3. [MCP 工具层 (`server.py`)](#3-mcp-工具层-serverpy)
4. [`WebUIManager` (`web/main.py`)](#4-webuimanager-webmainpy)
5. [`WebFeedbackSession` (`web/models/feedback_session.py`)](#5-webfeedbacksession-webmodelsfeedback_sessionpy)
6. [HTTP / WS 路由 (`web/routes/main_routes.py`)](#6-http--ws-路由-webroutesmain_routespy)
7. [前端模块地图](#7-前端模块地图)

---

## 1. CLI 入口 (`__main__.py`)

`python -m mcp_feedback_enhanced` 或 `uv run mcp-interactive-feedback` 的
argparse 入口。v3.0 后的子命令：

| 子命令 | 用途 | 状态 |
| --- | --- | --- |
| `serve [--http] [--host 127.0.0.1] [--port 8765] [--log-level info]` | 启动 HTTP 多会话 daemon（**推荐**） | 稳定 |
| `server` | 以 stdio 方式启动 MCP 服务器 | 过渡保留，将在后续阶段移除 |
| `test [--web] [--desktop] [--timeout 60]` | 诊断/自检 | 保留 |
| `version` | 打印版本 | 保留 |

**关键参数**

- `--host` 默认 `127.0.0.1`；若跨主机使用，请搭配 SSH 端口转发或显
  式绑到可信内网 IP（另见 `ssh-remote/` 指南）。
- `--port` 默认 `8765`，**被占用时直接失败**（不做自动 +1 试探），
  方便外部 Agent 用固定 URL。

---

## 2. HTTP Daemon (`daemon.py`)

唯一进程，把 FastMCP + FastAPI 合并进同一个 uvicorn 进程。

```python
def build_daemon_app(manager: WebUIManager) -> FastAPI: ...
def serve_http(
    *, host: str, port: int, log_level: str,
) -> None: ...
```

**`build_daemon_app`** 的职责：

1. 创建 `WebUIManager` 单例。
2. 用 `FastMCP.http_app()` 获取 MCP 的 ASGI sub-app，挂在
   `/mcp/`（Streamable HTTP 传输）。
3. 挂载 FastAPI 路由（`routes/main_routes.py`，图片上传通过
   `submit_feedback` 的内嵌 base64 字段处理，无独立图片上传接口）。
4. 注入 startup/shutdown 钩子，绑定到 `WebUIManager` 的初始化与清理。
5. 返回已装配完毕的 FastAPI 应用。

**`serve_http`** 在 `build_daemon_app` 外层启动 uvicorn：

- 使用 `uvicorn.run(app, host=host, port=port, log_level=log_level)`
  阻塞运行。

---

## 3. MCP 工具层 (`server.py`)

只暴露一个工具 `interactive_feedback`：

```python
async def interactive_feedback(
    project_directory: str,
    summary: str,
    timeout: int = 600,
    title: str | None = None,
) -> list[TextContent | ImageContent]: ...
```

职责：

1. 调用 `launch_web_feedback_ui(project_directory, summary, timeout, title)`
   生成新 session 并 **按 `session_id` 精确查找** 该会话
   （修复 sticky-active 下的串线 bug，见
   [`multi-session-http-redesign.md`](./multi-session-http-redesign.md)
   §8「Phase 3 实际落地差异与经验教训」一节）。
2. 调用 `session.wait_for_feedback(timeout)` 阻塞到用户提交 / 超时。
3. 把 `feedback` 文本 + 图片打包成 MCP 的 `TextContent`/`ImageContent`
   列表返回给 Agent。

`launch_web_feedback_ui` 不再自动打开浏览器（v3.0 是 daemon 模式，
用户浏览器已常驻）。

---

## 4. `WebUIManager` (`web/main.py`)

进程级单例，保存所有运行时状态。核心字段（简化）：

```python
class WebUIManager:
    sessions: dict[str, WebFeedbackSession]
    _session_creation_order: dict[str, int]
    _creation_seq: int                 # 单调计数，稳定排序 tie-breaker
    _active_session_id: str | None     # 前端当前视图（粘滞）
    connections: set[WebSocket]        # 所有复用中的客户端
    global_active_tabs: dict           # 浏览器 tab 聚合
    _pending_session_update: bool
```

### 4.1 会话管理

| 方法 | 说明 |
| --- | --- |
| `create_session(project_directory, summary, title=None)` | **插入式**创建；不销毁旧会话，不抢占 `_active_session_id`（粘滞活跃指针） |
| `get_session(session_id)` | 按 ID 精确查找 |
| `get_current_session()` | 返回 `_active_session_id` 指向的会话；前端视图专用 |
| `remove_session(session_id)` | 物理删除（伴随 `_session_creation_order` 清理） |
| `clear_current_session()` | 归档/清空当前会话 |
| `cancel_session(session_id, reason=None)` | 主动取消；若取消的是当前活跃会话，由 `_select_fallback_active_session` 挑一个合适的接替者 |

### 4.2 连接与广播

| 方法 | 说明 |
| --- | --- |
| `register_connection(ws)` / `unregister_connection(ws)` | 维护 `connections` 集合 |
| `broadcast(event)` | 向所有 WS 连接推送事件；返回成功投递数 |
| `broadcast_session_event(session_id, type, payload)` | 封装为 `{session_id, type, data}` 的多路复用事件 |
| `build_sessions_snapshot()` | 返回按 `created_at DESC` + `_creation_seq DESC` 排序的会话摘要列表（REST `/api/sessions` 与 WS 初次同步共用） |

### 4.3 粘滞活跃指针规则

`create_session` 的判定：

```
prior_active_valid = (
    self._active_session_id is not None
    and self._active_session_id in self.sessions
    and self._active_session_id != new_session_id
)
if not prior_active_valid:
    self._active_session_id = new_session_id
```

- 所以「新会话到来是否抢占视图」完全由前端的 `set_active_session`
  控制，后端只做兜底。

### 4.4 清理策略

- `cleanup_expired_sessions()`：定期清理超过保留期、已终态的会话；
- `cleanup_sessions_by_memory_pressure(force=False)`：内存压力触发；
- `_scan_expired_sessions()`：返回待清理 ID 列表，供以上两者复用。

---

## 5. `WebFeedbackSession` (`web/models/feedback_session.py`)

单个会话的状态机 + 数据载体。

```python
class SessionStatus(Enum):
    WAITING                 # 等待用户提交
    ACTIVE                  # 用户已切换到此会话（可选态）
    FEEDBACK_SUBMITTED      # 已提交，等 MCP 端收口
    COMPLETED               # wait_for_feedback 已返回
    ERROR / TIMEOUT / EXPIRED / CANCELED
```

关键公开接口：

| 方法 | 作用 |
| --- | --- |
| `wait_for_feedback(timeout)` | 阻塞，等 `feedback_completed` 事件；命中超时触发 `_cleanup_resources_on_timeout` |
| `submit_feedback(text, images, settings)` | 写入结果，设置 `feedback_completed`，广播 `feedback_received` |
| `add_user_message(msg)` / `add_log(entry)` | 用户消息、执行日志的累加 |
| `run_command(command)` | （遗留）允许页面执行命令；在日志中回显 |
| `cancel(message)` / `set_error(message)` / `set_expired(message)` | 终态转移 |
| `next_step(message=None)` | 状态机显式推进（例如 WAITING → ACTIVE） |
| `is_active()` / `is_terminal()` / `is_expired()` | 状态查询 |
| `get_status_info()` / `get_cleanup_stats()` | 给 `/api/sessions*` 用的摘要 |
| `extend_cleanup_timer(additional_time=None)` | 延长闲置保留期 |

内部组件：

- `_broadcast_event`：会话级广播，走 `manager.broadcast_session_event`。
- `_cleanup_resources_enhanced(reason)` / `_cleanup_sync_enhanced`：
  根据 `CleanupReason` 做不同力度的资源释放（异步 + 同步版，互为兜底）。
- `_schedule_auto_cleanup()`：按空闲时间/超时调度自动清理。

---

## 6. HTTP / WS 路由 (`web/routes/main_routes.py`)

`setup_routes(manager)` 里注册所有 HTTP / WS 端点。主要路由：

| 路径 | 方法 | 用途 |
| --- | --- | --- |
| `/` | GET | SPA 外壳（`feedback.html`）；v3.0 不再有单独的等待页 |
| `/api/translations` | GET | i18n JSON |
| `/api/session/status` | GET | 当前活跃会话状态（旧接口，保留） |
| `/api/current-session` | GET | 当前活跃会话详情（兼容） |
| `/api/all-sessions` | GET | 全部会话摘要（兼容） |
| `/api/sessions` | GET | **新主接口**，返回 `{active_session_id, sessions:[...]}` |
| `/api/sessions?status=STATUS` | DELETE | 按状态批删 |
| `/api/sessions/{session_id}/archive` | POST | 手动归档单个会话 |
| `/api/user-message` | POST | 追加一条用户补充消息 |
| `/api/settings` (GET/POST) · `/api/settings/clear` | 前端设置同步 |
| `/api/session-history` (GET/POST) | 历史记录读写 |
| `/api/log-level` (GET/POST) | 运行时调日志级别 |
| `/ws?lang=zh-TW` | GET (upgrade) | **多路复用 WebSocket** |

`websocket_endpoint` 将新连接 `register_connection` 后进入 `recv → dispatch` 循环，
由 `handle_websocket_message_mux` 做顶层路由，再根据消息类型进入
`handle_websocket_message`（会话级兼容分发）。

### 客户端 → 服务端消息一览

`handle_websocket_message_mux` 处理的顶层类型：

- `set_active_session { session_id }` —— 同步 `_active_session_id`，回
  `active_session_ack`；
- `ping` —— 心跳；
- `set_language { lang }` —— 翻译缓存；
- 其他带 `session_id` 的类型（`submit_feedback` / `run_command` /
  `cancel_feedback` / `user_message` 等），先按 `session_id` 定位会话，
  再交给 `handle_websocket_message`。

### 服务端 → 客户端广播

统一格式 `{type, session_id?, data}`：

| type | 触发点 | 备注 |
| --- | --- | --- |
| `sessions_snapshot` | 连接建立 / 刷新 | 一次性推送全部会话 |
| `session_created` | `create_session` | 同时供前端判断是否挂 pending |
| `session_updated` | 状态/内容变更 | 包含新的 `status`、`summary`、标签等 |
| `session_removed` | 归档 / 清理 | 前端从侧栏抹掉 |
| `feedback_received` | 用户提交 | 成功响应；也是浏览器显示 toast 的依据 |
| `active_session_ack` | 响应 `set_active_session` | 带 `ok`、`session_id` |
| `server_shutdown` | `_delayed_server_stop` | 关停提示 |

详细 payload 字段见 [`api-reference.md`](./api-reference.md)。

---

## 7. 前端模块地图

根模板：`web/templates/feedback.html`（SPA 外壳）。静态资源位于
`web/static/js/` 与 `web/static/css/`。

根模板 `feedback.html` 的结构也被 v3.0 重排为 **3 层信息架构**——顶栏
放应用级按钮（设定 / 关于），左栏放会话列表 + 底部的「会话历史」入口，
右侧 Tab 栏**只保留真正会话级**的内容（工作区 / AI 摘要 / 命令）。
详细使用见 [`phase3-multi-session-ui-usage.md §3`](./phase3-multi-session-ui-usage.md)。

| 模块 | 职责 |
| --- | --- |
| `app.js` | 应用入口，串起 WS、session-store、UI manager、侧栏、提交流程；维护 `_drafts` 每会话草稿、`_lastActiveSessionId` 切换跟踪、`_syncFeedbackStateToSession` 后端状态映射 |
| `modules/session-store.js` | 全部会话的响应式数据源；暴露 `ACTIVE_CHANGED` / `SESSION_ADDED` / `SESSION_UPDATED` / `SESSION_REMOVED` 事件 |
| `modules/session-sidebar.js` | 左侧会话卡片渲染；创建时间倒序排序；状态徽标、pending 圆点、WAITING 会话脉冲动画；点击触发 `set_active_session` |
| `modules/websocket-manager.js` | WS 连接管理、重连、顶层消息分发到 `sessionStore`；新会话到来时根据「当前是否有其它会话活跃」决定是否挂 `has_pending_notification` |
| `modules/notify-badge.js` | 标题 `(N)` 前缀、Canvas 画 favicon 红点、`Notification` 系统弹窗；`Cmd/Ctrl+1..9` 按 `created_at DESC` 切换会话，顺序与侧栏一致；`MutationObserver` 守护标题前缀不被其他代码覆盖 |
| `modules/ui-manager.js` | 表单禁用/启用、按钮文案；识别 `FEEDBACK_NO_SESSION` 态；与 `app._setFeedbackFormDisabled` 协同 |
| `modules/utils.js` | 常量/工具；新增 `FEEDBACK_NO_SESSION` |
| `modules/app-shell-modal.js` | **v3.0 新增**。声明式应用模态开关器：`[data-modal-open]` / `[data-modal-dismiss]` 属性即可驱动模态开关；Esc/backdrop 关闭；同一时刻只开一个；`body.app-modal-open` 锁页面滚动。暴露 `open/close/closeAll/getCurrent` 4 个 API 供脚本使用 |
| `modules/connection-monitor.js` | 连接状态监控（连接时长、重连次数、消息数、延迟）。v3.0 起直接读 `MCPFeedback.sessionStore` 计算会话数与当前状态，并启动 1 秒 display ticker，让指示器 tooltip 不会因为没有事件到来而冻结；v3.0.x 把原「浮动统计面板」去掉，改为把所有指标聚合到顶栏 `#connectionStatusMinimal` 的 tooltip 里 |
| `modules/image-handler.js` · `modules/file-upload-manager.js` | 图片/文件上传、粘贴板兼容 |
| `modules/tab-manager.js` · `modules/settings-manager.js` · `modules/audio` · `modules/prompt` · `modules/session` · `modules/session-manager.js` · `modules/logger.js` · `modules/constants` · `modules/utils` · `modules/textarea-height-manager.js` | 其他功能/兼容模块，沿用 v2.x 设计 |

前端 CSS 变动：

- `web/static/css/session-sidebar.css` — 侧栏样式、pending 圆点、
  WAITING 脉冲动画，以及 v3.0 新增的 `.sidebar-footer` / `.sidebar-footer-btn`
  底部「会话历史」按钮样式。
- `web/static/css/styles.css` — v3.0 新增通用应用模态样式
  （`.app-modal` / `.modal-backdrop` / `.modal-content` 等，含淡入/滑入
  动画）、顶栏图标按钮（`.topbar-actions` / `.topbar-icon-btn`）、
  工作区小图标按钮（`.section-header-actions` / `.btn-icon-sm`）。
- `body.app-modal-open` 配合 `AppShellModal` 锁定页面滚动。

---

**文档版本**：v3.0.0-dev · **最后更新**：2026-04-23
