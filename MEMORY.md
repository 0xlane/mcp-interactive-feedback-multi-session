# Project Memory

> 面向 AI 协作的项目上下文索引。首次接触本仓库或需要唤起上下文时，按以下指引阅读相关文档即可。

## 当前状态

**v3.0 多会话 HTTP 模式重构** — 已**全部落地**（Phase 1 / 2 / 3 完成）。

- 架构总入口：[`docs/architecture/README.md`](./docs/architecture/README.md)
- 设计背景 + 经验教训：[`docs/architecture/multi-session-http-redesign.md`](./docs/architecture/multi-session-http-redesign.md)
- 最新 UI 使用指南：[`docs/architecture/phase3-multi-session-ui-usage.md`](./docs/architecture/phase3-multi-session-ui-usage.md)

### v3.0 里程碑

- ✅ **Phase 1**（后端多会话化）：`WebUIManager.create_session` 改为插入式，不再销毁旧会话；每次 MCP 调用注册一个 `WebFeedbackSession`
- ✅ **Phase 2**（HTTP Daemon）：`uv run mcp-interactive-feedback serve --http` 单实例常驻；FastMCP Streamable HTTP 挂在 `/mcp/`；PID 锁 + 固定端口 `127.0.0.1:8765`
- ✅ **Phase 3 (UI)**：单浏览器页面 + WebSocket 多路复用 + 双栏 SPA；粘滞活跃指针；每会话独立草稿；`Cmd/Ctrl+1..9` 快捷键；红点/`(N)` 标题/Favicon/桌面通知 四层 pending
- ✅ **3 层信息架构**（最后一轮 UI 整理）：顶栏放应用级动作（⚙️ 设定 / ℹ️ 关于）、左栏底部放 🗂️ 会话历史、右栏 Tab 仅保留会话级内容（工作区（AI 摘要嵌入其中）/ 命令）

### 关键决策回顾

- **破坏性变更**：v3.0 完全移除 stdio 模式，用户必须改 `mcp.json` 指向 HTTP URL
- **本仓库是自用分支**：不发布到 PyPI，没有 CI；部署只有源码路径（`git clone` + `uv sync` + `uv run`）
- 启动方式：用户手动（`uv run`），不提供 LaunchAgent/systemd
- 绑定：`127.0.0.1:8765` 默认；端口占用直接报错
- 认证：本地单用户，不启用 Token
- 会话标识：MCP tool 新增 `title` 可选参数；缺省使用 project 目录 basename
- **粘滞活跃**：新会话到达**不**抢前端视图，只打侧栏红点 + `(N)` 标题 + 系统通知
- **归档语义**：`X` 按钮 = 后端字典物理删除（不是 UI 隐藏）
- Tauri 桌面模式：v3.0 起停止构建（源码保留在 `src-tauri/` 仅作参考）

## 快速索引

| 目的 | 看这里 |
|---|---|
| 我是新人，想快速理解 v3.0 | [`docs/architecture/README.md`](./docs/architecture/README.md) |
| 我要把 daemon 跑起来 | [`docs/architecture/phase2-http-daemon-usage.md`](./docs/architecture/phase2-http-daemon-usage.md) |
| 我要在浏览器里用它 | [`docs/architecture/phase3-multi-session-ui-usage.md`](./docs/architecture/phase3-multi-session-ui-usage.md) |
| 我要改后端 | [`docs/architecture/component-details.md`](./docs/architecture/component-details.md) |
| 我要改前端 | [`docs/architecture/component-details.md` §8](./docs/architecture/component-details.md#8-前端模块地图) |
| MCP 工具 / REST / WebSocket 协议 | [`docs/architecture/api-reference.md`](./docs/architecture/api-reference.md) |
| 部署 / SSH 远程 / launchctl | [`docs/architecture/deployment-guide.md`](./docs/architecture/deployment-guide.md) + [`docs/zh-CN/ssh-remote/`](./docs/zh-CN/ssh-remote/) |
| 交互时序 / 序列图 | [`docs/architecture/interaction-flows.md`](./docs/architecture/interaction-flows.md) |
| 本 fork 的 CHANGELOG | [`RELEASE_NOTES/CHANGELOG.zh-CN.md`](./RELEASE_NOTES/CHANGELOG.zh-CN.md)（只含 v3.0.0 起的 fork 历史；上游 v2.x 不在范围） |

## 关键实现文件

后端：
- `src/mcp_feedback_enhanced/server.py` — MCP 入口 + `interactive_feedback` tool
- `src/mcp_feedback_enhanced/web/main.py` — `WebUIManager` 单例（含粘滞活跃逻辑）
- `src/mcp_feedback_enhanced/web/daemon.py` — `serve_http()` + PID 锁
- `src/mcp_feedback_enhanced/web/routes/main_routes.py` — FastAPI 路由、`/ws` 多路复用
- `src/mcp_feedback_enhanced/web/models/feedback_session.py` — 会话状态机
- `src/mcp_feedback_enhanced/__main__.py` — CLI (`serve --http` 子命令)

前端：
- `src/mcp_feedback_enhanced/web/static/js/app.js` — 应用入口 + 每会话草稿
- `src/mcp_feedback_enhanced/web/static/js/modules/session-store.js` — 响应式数据源
- `src/mcp_feedback_enhanced/web/static/js/modules/session-sidebar.js` — 左侧会话列表
- `src/mcp_feedback_enhanced/web/static/js/modules/websocket-manager.js` — WS 多路复用
- `src/mcp_feedback_enhanced/web/static/js/modules/notify-badge.js` — 标题/favicon/系统通知
- `src/mcp_feedback_enhanced/web/static/js/modules/app-shell-modal.js` — 应用模态统一开关器（v3.0 新增）
- `src/mcp_feedback_enhanced/web/static/js/modules/connection-monitor.js` — 连接监控面板
- `src/mcp_feedback_enhanced/web/templates/feedback.html` — 3 层 UI 主模板

## 开发约定

- 文档语言：既有架构文档保留**繁体中文**头部索引，详细内容用**简体中文**（开发者日常沟通语言）；UI 层支持三语（zh-TW / zh-CN / en）
- 提交规范：Conventional Commits（`refactor(web):` / `fix(web):` / `chore(repo):` / `docs:` 等），commit body 给出"为什么"而非"做了什么"
- 测试入口：`uv run pytest`（完整 `202 passed`；详见 `tests/`）
- 静态文件改动**必须**同步 bump `feedback.html` 里 `<script src="...?v=YYYYMMDDNN">` 的 cache buster
