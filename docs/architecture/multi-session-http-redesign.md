# 多会话 HTTP 模式重构设计

> **状态**：设计已定稿，待进入实施
> **创建日期**：2026-04-22
> **最后更新**：2026-04-22（所有决议事项已确认，见 §10）
> **涉及范围**：MCP 传输层、Web UI 管理层、前端交互层
> **预期版本**：v3.0.0（**破坏性变更**：完全移除 stdio 模式，不保留兜底）

## 1. 背景

### 1.1 现状痛点

当前项目 (`v2.6.0`) 采用 **"stdio MCP + 单活跃会话 + 每进程一端口"** 的架构：

- 每个 AI Agent（Cursor / Claude Code / Windsurf / ...）通过 stdio 拉起一个独立的 `mcp-interactive-feedback` 子进程；
- 每个子进程里 `WebUIManager` 是**单例**，启动自己的 FastAPI+uvicorn 服务器，监听独立端口（默认 `8765`，冲突时自动递增）；
- 每次 `interactive_feedback` 工具被调用，会在当前进程里创建会话，并**打开一个新浏览器 Tab**（或复用同进程内已有 Tab）;
- 同一进程内多次调用遵循"单活跃会话 + WebSocket 迁移"语义：新会话挤掉旧会话，WS 被转移，前端刷新显示新会话。

由此产生的用户可观察问题：

| 痛点 | 根因 |
|---|---|
| 一个用户常年能看到十几个 `MCP Feedback` 浏览器 Tab | N 个 Agent → N 个进程 → N 个端口 → N 个 Tab |
| 切换 Tab 时找不到哪个在等反馈 | 没有全局入口，每个 Tab 只知道自己进程里的会话 |
| Cursor IDE 多 Chat 并行时配置文件写冲突 | `session_history.json` / `ui_settings.json` 被多个进程同时写 |
| 端口随机化导致难以用固定 URL 访问 | `PortManager.find_free_port_enhanced` 自动递增 |
| 关掉 Tab 会误伤正在等待的 Agent | Tab 与进程生命周期未解耦 |

### 1.2 需求目标

1. **单实例多会话**：全机器/单用户只保留一个守护进程；
2. **HTTP 传输**：AI Agent 侧通过 HTTP 连接 MCP，不再 fork 子进程；
3. **单浏览器页面聚合所有会话**：用户只面对一个 Tab 即可处理来自任意 Agent 的反馈请求；
4. **明确的会话切换、通知、归档语义**；
5. **在不损失现有功能**（命令执行、图片上传、Markdown 摘要、i18n、音效、通知、桌面模式）**的前提下完成**。

## 2. 技术可行性

**可行**，且改造路径与现有代码高度契合：

| 现有能力 | 对新架构的贡献 |
|---|---|
| FastAPI + uvicorn 已做后端 | 直接作为 HTTP 容器，FastMCP 2.x 原生支持挂载到 FastAPI |
| `sessions: dict[str, WebFeedbackSession]` 多会话容器已存在 | 去掉 `current_session` 包装层即可复用 |
| `/api/all-sessions` 已能返回全量会话 | 新 UI 的侧栏数据源 |
| `WebFeedbackSession` 状态机、清理管理器、内存监控器 | 全部复用，仅需少量语义调整 |
| `notification-manager.js`、`audio-manager.js`、i18n、Markdown 渲染 | 全部复用 |
| Tauri 桌面壳是个 WebView 套 URL | HTTP 改造对它透明 |

主要变更集中在：**传输层切换、进程模型、`current_session` 语义解除、前端改双栏、新增归档 API**。

## 3. 目标架构

### 3.1 进程模型对比

#### 当前（单进程单会话）

```mermaid
graph LR
  subgraph "Cursor"
    C1[Chat 1]
    C2[Chat 2]
  end
  subgraph "Claude Code"
    C3[Task 3]
  end
  subgraph "Desktop"
    B1[Browser Tab :8765]
    B2[Browser Tab :8766]
    B3[Browser Tab :8767]
  end
  C1 -.stdio.-> P1[mcp-server #1<br/>port 8765]
  C2 -.stdio.-> P2[mcp-server #2<br/>port 8766]
  C3 -.stdio.-> P3[mcp-server #3<br/>port 8767]
  P1 --> B1
  P2 --> B2
  P3 --> B3
  style P1 fill:#fee
  style P2 fill:#fee
  style P3 fill:#fee
```

#### 目标（单守护多会话）

```mermaid
graph LR
  subgraph "Cursor"
    C1[Chat 1]
    C2[Chat 2]
  end
  subgraph "Claude Code"
    C3[Task 3]
  end
  subgraph "User"
    B[Single Browser Tab :8765]
  end
  C1 -.http.-> D
  C2 -.http.-> D
  C3 -.http.-> D
  D[mcp-feedback-daemon<br/>FastAPI :8765<br/>/mcp + /ws + /] --> B
  style D fill:#efe
  B -. switch .-> S1[Session 1]
  B -. switch .-> S2[Session 2]
  B -. switch .-> S3[Session 3]
```

### 3.2 四层架构对照

| 层 | 当前实现 | 目标实现 |
|---|---|---|
| MCP 服务层 | `mcp.run()` 默认 stdio | `mcp.run(transport="http")` 或挂载为 FastAPI 子应用 |
| Web UI 管理层 | `WebUIManager.current_session` 单活跃 | `WebUIManager.sessions` 多会话字典，无 current 概念 |
| Web 服务层 | 每进程独立 uvicorn | 单守护进程，FastMCP 与 Web UI 共享 ASGI 应用 |
| 前端交互层 | 单页单会话（`feedback.html` 嵌入当前会话数据） | 双栏布局（左会话列表 + 右详情），WS 多路复用 |

## 4. 影响矩阵

### 4.1 需要删除 / 重构

| 位置 | 原因 |
|---|---|
| `WebUIManager.current_session` 相关字段与方法 | 多会话下无此概念 |
| `WebUIManager.create_session` 中"旧会话转 COMPLETED + WebSocket 迁移给新会话"（`web/main.py:335-404`） | 新会话不应挤掉旧会话 |
| `WebUIManager.smart_open_browser` 中的刷新通知逻辑 | 改为"无 WS 连接时才开 Tab" |
| `WebUIManager._pending_session_update` | 改为向所有 WS 广播 `session_created` 事件 |
| `WebUIManager.notify_existing_tab_to_refresh` | 语义变为"广播 session 列表变更" |
| `/` 路由根据 `current_session` 返回不同模板 | 改为总是返回"会话列表壳"，数据前端拉取 |
| `/ws` 隐式绑定 `manager.get_current_session()`（`routes/main_routes.py:258-276`） | 改为多路复用，消息携带 `session_id` |
| `/api/session-status`、`/api/current-session`（或保留仅供兼容） | 冗余，被 `/api/sessions` 取代 |
| `launch_web_feedback_ui` 中的"懒启动服务器 + 每次开浏览器" | 守护模式下服务器常驻 |
| `PortManager.find_free_port_enhanced` 在守护模式下的"自动切换端口" | 守护模式端口必须固定，冲突时应报错而非递增 |
| `session-data-manager.js` "新会话来 → 旧会话进历史记录"（`session/session-data-manager.js:54-93`） | 多会话下旧会话应继续存在 |
| `feedback_session.py:submit_feedback` 中"桌面模式提交后立即关窗" | 桌面模式改为常驻窗口 |

### 4.2 需要新增

**后端**

- `mcp-interactive-feedback serve --http [--host 127.0.0.1] [--port 8765]` 子命令
- 单实例锁（PID 文件 + 端口占用检测）
- FastAPI 挂载 MCP ASGI 子应用
- 新 API：
  - `GET /api/sessions` — 活跃 + 最近完成的全量会话（已有 `/api/all-sessions`，扩展字段即可）
  - `POST /api/sessions/{sid}/submit` — REST 入口提交反馈（补 WS）
  - `POST /api/sessions/{sid}/archive` — 手动归档/取消
  - `DELETE /api/sessions?status=completed` — 批量清理
- WebSocket 多路复用协议（见 §5.2）
- 客户端断连探测（FastMCP 可感知 HTTP 请求断开，用于主动释放 `wait_for_feedback`）
- 优雅关机：收到 SIGTERM 时通知所有 WS + 让所有 WAITING 会话返回

**前端**

- `SessionSidebar` 组件（左栏）
- `SessionDetailPane`（右栏，复用现有 `feedback.html` 的反馈 UI）
- 每会话 state 隔离（草稿、未提交图片、命令输出缓存）
- 标题栏与 favicon 红点徽标
- 归档按钮（含二次确认分支）
- 音效/浏览器通知接线到 `session_created` 事件

**配置与文档**

- `mcp.json` 迁移示例（stdio → http url）—— 让用户手动替换
- 启动命令使用说明（README / 用户指南）

### 4.3 保留不动

- `WebFeedbackSession` 核心状态机与清理逻辑
- 图片处理、命令执行、Markdown 渲染、i18n、音效、通知管理器
- `session_cleanup_manager`、`memory_monitor`、`resource_manager`
- Tauri 桌面壳（仅需去掉"提交即关窗"分支）

## 5. 关键技术设计

### 5.1 MCP HTTP 传输与 FastAPI 合并

推荐方式：把 MCP 作为 ASGI 子应用挂到现有 FastAPI 上，共享端口。

```python
from fastmcp import FastMCP
from fastapi import FastAPI

mcp = FastMCP("interactive-feedback")

@mcp.tool()
async def interactive_feedback(...):
    ...

# 生成 MCP 的 ASGI 应用
mcp_app = mcp.http_app(path="/mcp")

# 使用其 lifespan 以确保 session manager 正确启动
app = FastAPI(lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)

# 原有路由继续注册到 app
setup_routes(app)
```

Agent 端的 `mcp.json` 由

```json
{
  "mcpServers": {
    "interactive-feedback": {
      "command": "uvx",
      "args": ["mcp-interactive-feedback"]
    }
  }
}
```

改为

```json
{
  "mcpServers": {
    "interactive-feedback": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

### 5.2 WebSocket 多路复用协议

一个浏览器 Tab 只开一个 `/ws` 连接。消息一律携带 `session_id`（广播类事件的 `session_id` 指示事件归属）。

**服务端 → 客户端**

| `type` | 说明 |
|---|---|
| `sessions_snapshot` | 连接建立时推送全量会话状态 |
| `session_created` | 新会话出现（由 MCP 工具调用触发） |
| `session_updated` | 会话状态变化（status/status_message/last_activity） |
| `session_feedback_submitted` | 某会话反馈已提交 |
| `session_archived` | 某会话被归档（终态或用户手动） |
| `session_expired` | 服务端清理过期会话 |
| `command_output` | 命令执行输出（带 `session_id`） |
| `command_complete` | 命令结束 |
| `notification` | 通用通知（沿用现有） |
| `server_shutting_down` | 优雅关机预告 |

**客户端 → 服务端**

| `type` | 说明 |
|---|---|
| `submit_feedback` | `{session_id, feedback, images, settings}` |
| `run_command` | `{session_id, command}` |
| `archive_session` | `{session_id}` |
| `cancel_session` | `{session_id}`（等同于归档 WAITING 态） |
| `heartbeat` | 心跳 |
| `subscribe` | 可选，用于未来做按需订阅 |

### 5.3 会话生命周期与归档

```mermaid
stateDiagram-v2
    [*] --> WAITING: MCP tool 调用创建
    WAITING --> ACTIVE: 浏览器打开并对焦该会话
    ACTIVE --> FEEDBACK_SUBMITTED: 用户提交反馈
    FEEDBACK_SUBMITTED --> COMPLETED: MCP tool 取走结果
    WAITING --> TIMEOUT: MCP tool 自身超时
    WAITING --> EXPIRED: 空闲超 max_idle_time
    WAITING --> CANCELED: 用户主动归档 WAITING 会话
    ACTIVE --> CANCELED: 用户主动归档 ACTIVE 会话
    COMPLETED --> [*]: 软可见期后清理
    TIMEOUT --> [*]: 同上
    EXPIRED --> [*]: 同上
    CANCELED --> [*]: 同上

    note right of WAITING
      显示红色等待点
      计入顶部 "N waiting" 徽标
    end note

    note right of FEEDBACK_SUBMITTED
      显示橙色已提交点
      等 MCP 拉结果
    end note

    note right of COMPLETED
      软可见期 30s
      然后折叠到历史
    end note
```

**归档语义矩阵**（对应用户"客户端未发结束事件时如何手动归档"的问题）：

| 触发时会话状态 | 归档语义 | 服务端动作 | UI 行为 |
|---|---|---|---|
| `WAITING` / `ACTIVE`（MCP tool 阻塞在 `wait_for_feedback`） | **取消**：让 Agent 拿到"用户取消" | 设 `feedback_result = None`，`feedback_completed.set()`，走清理；MCP tool 返回 `TextContent("用户取消了反馈。")` | 二次确认弹窗 |
| `FEEDBACK_SUBMITTED`（已提交，MCP 尚未取走） | 几乎不触发；触发则仅 UI 隐藏，服务端保留 | 仅标记 UI 隐藏 | 无确认 |
| `COMPLETED` / `TIMEOUT` / `EXPIRED` / `ERROR`（终态） | 纯 UI 清理 | 从 `sessions` 字典移除，写入 `session_history.json` | 无确认 |

**自动归档流程**：

1. 会话进入终态 → UI 侧栏保持 **软可见期**（默认 30s，可配置）显示"✓ 刚刚完成"；
2. 软可见期后折叠到"最近历史"区域（默认最多保留 10 条，可展开）；
3. `session_cleanup_manager` 周期扫描，终态且超过 N 分钟（默认 5）的会话从内存移除，metadata 追加写到 `session_history.json`。

**孤儿检测**（MCP 客户端异常断连，服务端不知情）：

- HTTP 传输下 FastMCP 可感知 `Request.is_disconnected()`；在 `wait_for_feedback` 循环中周期检查（如每 5s），一旦客户端消失主动释放会话；
- 兜底：现有 `max_idle_time` 默认 3600s 过期清理。

### 5.4 前端双栏 UI

```
┌───────────────────────────────────────────────────────────────┐
│  MCP Feedback                ● 2 waiting       [设置][主题][?]│
├───────────────────┬───────────────────────────────────────────┤
│  会话                │  项目：/path/to/backend                  │
│                   │  Agent：Cursor · 32s ago                   │
│  ● backend (32s)  │  ────────────────────────────────────────── │
│  ● frontend (8s)  │  ## AI 摘要                                │
│  ○ api-docs       │  （Markdown 渲染，支持复制）               │
│  ✓ refactor (刚完成)│                                          │
│  ────             │  ────────────────────────────────────────── │
│  历史（3）▾       │  你的反馈：                                │
│                   │  [textarea，每会话独立草稿]                │
│  [清空已完成]      │  [图片上传]  [命令执行]                    │
│                   │  [提交]       [取消此会话]                 │
└───────────────────┴───────────────────────────────────────────┘
```

**排序规则**：
- 第一组：`WAITING` / `ACTIVE`（红点 / 实心圆），按"等待时间最久"降序；
- 第二组：`FEEDBACK_SUBMITTED`（橙点），按时间降序；
- 第三组：终态（灰勾 / 灰叉），按时间降序；折叠到"历史"。

**切换体验**：
- 点击左栏只改右栏，无 URL 跳转（可选 `#session-id` hash 以支持刷新恢复）；
- 切换时自动保存当前草稿（`localStorage["draft:" + sid]`）；
- 键盘：`⌘/Ctrl + 1..9` 跳到第 N 个；`⌘/Ctrl + Enter` 提交；`Esc` 归档当前。

**通知堆叠**（从弱到强，默认全开，可在设置里按需关闭）：

1. `document.title` = `(N) MCP Feedback` — N 为等待中数量；
2. Favicon 红点（Canvas 动态绘制）；
3. 侧栏脉动动画；
4. 浏览器 Desktop Notification（复用 `notification-manager.js`，仅页面失焦/隐藏时触发，已具备）；
5. 音效（复用 `audio-manager.js`，默认关闭以免打扰）；
6. （Tauri 桌面模式）Dock / Taskbar 徽标 `app.set_badge_count(N)`。

### 5.5 会话标识

使用场景是 Cursor IDE / Cursor CLI，为此给 `interactive_feedback` tool 加一个**可选的会话标题**参数，让 AI 自己起一个人类可读的短标题（比如当前任务主题）：

```python
@mcp.tool()
async def interactive_feedback(
    project_directory: str = ".",
    summary: str = "...",
    timeout: int = 3600,
    title: str | None = None,  # 新增：会话标题，用于侧栏识别
) -> list: ...
```

**UI 侧栏显示规则**：

- 主文：`title`（AI 传入）或 `basename(project_directory)`（未传入时兜底）
- 副文：`summary` 截断到 50 字
- 状态点：颜色 + 文字（`● 等待 · 32s` / `● 进行中` / `✓ 刚完成`）

Prompt 里建议引导 AI 用短语做标题（如 `"修复登录重定向"`、`"API 文档补全"`），而不是冗长描述。文档/示例会在用户指南里给出样板。

## 6. 启动与运行模型

### 6.1 启动方式

**保持与当前一致**——用户手动执行一条命令即可，不提供 LaunchAgent / systemd / Task Scheduler 等服务化方案（个人本地使用场景，保持简单）：

```bash
# 首次使用前手动启动一次，进程常驻
uvx mcp-interactive-feedback serve --http

# 或通过 pip 安装后
mcp-interactive-feedback serve --http
```

参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--host` | `127.0.0.1` | 固定绑本地回环，不对外暴露 |
| `--port` | `8765` | 固定端口，冲突时直接报错退出 |

### 6.2 单实例锁

- `~/.config/mcp-feedback-enhanced/daemon.pid` 写入 PID；
- 启动时检测：PID 存在且进程仍在 → 拒绝启动并提示已在运行；
- PID 存在但进程已死 → 清理后继续；
- 端口被占 → 不自动切换端口，直接报错提示用户手动处理。

### 6.3 鉴权

**不启用**。使用场景是本地单用户（`127.0.0.1`），无需 Token。

### 6.4 Agent 端配置

用户手动把 `mcp.json` 从 stdio 形式改为 HTTP 形式（见 §5.1 示例）。不提供自动迁移命令。stdio 模式**不保留兜底**——直接在 v3.0 切换，改造彻底。

## 7. 未提但需考虑的问题清单（含决议）

| # | 问题 | 最终决议 |
|---|---|---|
| 1 | Agent 身份识别 | 新增 `title` 可选参数；未传则用 `basename(project_directory)` 兜底。见 §5.5 |
| 2 | URL Token 鉴权 | **不启用**。仅绑 `127.0.0.1`，本地单用户不需要 |
| 3 | 首次浏览器 Tab 打开时机 / 竞态 | `asyncio.Lock` 包住"检测 WS + 开 Tab"，无 WS 时才 `webbrowser.open` |
| 4 | Tab 关闭后再次 MCP 调用 | 同 #3，自动重开 |
| 5 | `session_history.json` 长期膨胀 | 限条数 500 + 尺寸 2MB + 大会话截断摘要 |
| 6 | 全局单守护 vs 按项目 | 仅全局单守护，不支持 `--instance-id`（个人本地使用，不做团队场景） |
| 7 | Tauri 桌面模式 | **暂停维护**。v3.0 发布只支持浏览器 Tab；源码保留，CI 不构建 desktop binary；README 明确说明 |
| 8 | 并发命令执行限流 | `max_concurrent_commands = 5`（全局默认），超限排队，不暴露配置开关 |
| 9 | 多会话自动化测试 | 新增并发创建 / WS 多路复用 / 归档解锁 `wait_for_feedback` 的集成测试 |
| 10 | 优雅关机 | SIGTERM → 广播 `server_shutting_down` → 所有 WAITING 返回 canceled → 写 history → 释放端口 |
| 11 | i18n 新词条 | 侧栏、归档、取消确认、批量操作——三语（zh-TW / zh-CN / en）全补 |
| 12 | `current_session` 代码引用范围 | 全局搜索 + 清除（包括 `tests/`、桌面模块）；无兼容包袱 |
| 13 | 历史会话数据隐私 | 沿用现有三级隐私控制，不新增 |
| 14 | 启动方式 | 保持与当前一致的用户手动命令启动（`uvx`/`pip`），不提供服务化部署模板 |
| 15 | 向后兼容 | **不保留 stdio 兜底**，v3.0 直接切换；用户手动改 `mcp.json` |

## 8. 分阶段落地路线

每阶段均可独立 merge 并保持功能可用。

### 阶段 1：后端多会话化（UI 暂不动）

- 移除 `current_session` 相关逻辑；
- 重写 `create_session` 为纯插入；
- `/ws` 改为多路复用；
- `/api/all-sessions` 字段补齐；
- 单元测试：并发创建 / 并发提交 / 归档 WAITING 解锁 `wait_for_feedback`。

**验收**：服务器能并发持有多个会话且相互不干扰；UI 暂时只显示最新会话（与现行外观一致）。

### 阶段 2：HTTP MCP 传输 + 守护模式

- `mcp.http_app()` 挂载；
- `serve --http` 子命令；
- PID 锁、端口冲突报错；
- `mcp.json` 迁移示例（README / 用户指南）。

**验收**：单守护进程可同时服务多个 Agent 的并发 MCP 调用。

### 阶段 3：前端双栏 UI

- `SessionSidebar` + `SessionDetailPane` 组件；
- WS 多路复用接线；
- 每会话草稿/命令输出隔离；
- Title / favicon / 音效 / 通知徽标。

**验收**：一个 Tab 内能流畅切换多个会话、看到等待中提示。

### 阶段 4：归档与清理语义

- 手动归档 API + UI 按钮；
- 归档与 `wait_for_feedback` 联动的取消语义；
- 孤儿会话主动检测；
- 历史文件瘦身。

**验收**：用户可手动取消等待中的会话并让 Agent 收到取消结果；长期运行不膨胀。

### 阶段 5：i18n + 测试 + 文档收尾

- 三语种翻译补全（新词条：侧栏、归档、取消确认等）；
- 集成测试完善；
- README / 用户指南：启动命令说明、`mcp.json` 改造示例、v3.0 breaking change 声明；
- **桌面模式**：在 README 顶部加 deprecation 提示；CI 去掉 Tauri 构建产物；源码保留不删，留作未来有需求时恢复。

**验收**：三语无漏词；CI 通过；用户可从 README 复制新的 `mcp.json` 配置一次跑通。

## 9. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| FastMCP 版本演进对 `http_app` API 破坏性变更 | 中 | 锁定最低版本范围，CI 矩阵覆盖多版本 |
| 单守护进程崩溃导致所有 Agent 失联 | 中 | 进程退出码明确；用户可在 IDE 里通过"重启 MCP"复跑命令；README 写 troubleshooting 指引 |
| 长期运行内存泄漏 | 中 | 已有 `memory_monitor`；多会话下新增压力测试用例 |
| WebSocket 多路复用消息混乱 | 中 | 所有事件强制携带 `session_id`；前端按 id 分发；TypeScript/JSDoc 类型标注 |
| 首次发布 v3.0 后用户 `mcp.json` 忘改 | 低（破坏性变更已声明） | README 顶部大字提示；启动时检测到 stdio 调用直接报 `stdio mode removed in v3.0` 错 |

## 10. 决议结论

所有原"待决议"事项已与用户确认，最终结论如下：

| 议题 | 结论 |
|---|---|
| 端口冲突策略 | 守护模式下固定端口，冲突即报错退出，不自动递增 |
| 会话软可见期时长 | 30s（硬编码），不做用户可配置 |
| 会话标识字段 | 新增 `title` **可选**参数；未传则用 `basename(project_directory)` 兜底 |
| Token 鉴权 | **不启用**。默认绑 `127.0.0.1`，本地单用户场景 |
| 桌面模式定位 | v3.0 暂停维护，只支持浏览器 Tab；Tauri 源码保留，CI 不再构建桌面产物 |
| stdio 兜底 | **完全移除**。v3.0 直接切换 HTTP，用户手动改 `mcp.json` |
| `session_history.json` 迁移 | 旧格式直接丢弃，用户重装即清空；无需兼容 |
| 启动方式 | 保持与当前一致的 `uvx` / `pip` 手动命令启动，不提供 LaunchAgent / systemd 等服务化方案 |
| 并发限制 | `max_concurrent_commands = 5` 全局硬编码，不做配置开关 |
| Agent 使用面 | 仅考虑 Cursor IDE / Cursor CLI，不做团队/多用户场景 |

---

## 附录 A：关键文件导航

| 文件 | 现有职责 | 改造重点 |
|---|---|---|
| `src/mcp_feedback_enhanced/server.py` | MCP 服务器入口、`interactive_feedback` tool | 切换 transport；与 FastAPI 合并 |
| `src/mcp_feedback_enhanced/web/main.py` | `WebUIManager` 单例 | 删除 `current_session`；改造 `create_session` |
| `src/mcp_feedback_enhanced/web/routes/main_routes.py` | FastAPI 路由、WS 端点 | 重写 `/`、`/ws`；新增 `/api/sessions/{sid}/archive` 等 |
| `src/mcp_feedback_enhanced/web/models/feedback_session.py` | `WebFeedbackSession` 状态机 | 小改：新增 `CANCELED` 状态，孤儿检测接口 |
| `src/mcp_feedback_enhanced/web/templates/index.html` | 等待页 | 改为双栏壳 |
| `src/mcp_feedback_enhanced/web/templates/feedback.html` | 反馈页 | 拆为右栏详情组件模板 |
| `src/mcp_feedback_enhanced/web/static/js/modules/websocket-manager.js` | WS 连接管理 | 改为多路复用 |
| `src/mcp_feedback_enhanced/web/static/js/modules/session/session-data-manager.js` | 会话数据 | 支持并发多会话；删"旧会话进历史"逻辑 |
| `src/mcp_feedback_enhanced/web/static/js/modules/session-manager.js` | 会话 UI | 重构为侧栏 + 详情双组件 |
| `src/mcp_feedback_enhanced/__main__.py` | CLI | 新增 `serve --http` 子命令 |

## 附录 B：WS 消息示例

```json
// 服务端 → 客户端：会话快照
{
  "type": "sessions_snapshot",
  "sessions": [
    {
      "session_id": "abc-123",
      "project_directory": "/path/to/backend",
      "summary": "...",
      "status": "waiting",
      "title": "修复登录重定向",
      "created_at": 1735000000000,
      "last_activity": 1735000030000
    }
  ]
}

// 客户端 → 服务端：提交反馈
{
  "type": "submit_feedback",
  "session_id": "abc-123",
  "feedback": "looks good",
  "images": [],
  "settings": {}
}

// 客户端 → 服务端：取消等待中的会话
{
  "type": "cancel_session",
  "session_id": "abc-123"
}

// 服务端 → 客户端：通知会话已归档
{
  "type": "session_archived",
  "session_id": "abc-123",
  "reason": "user_canceled"
}
```

---

**维护者**：待定
**相关文档**：
- `docs/architecture/system-overview.md`（现架构总览，升级后需更新）
- `docs/architecture/api-reference.md`（API 变化记录）
- `MEMORY.md`（AI 协作上下文索引）
