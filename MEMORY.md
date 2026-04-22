# Project Memory

> 面向 AI 协作的项目上下文索引。首次接触本仓库或需要唤起上下文时，按以下指引阅读相关文档即可。

## 当前重点

**多会话 HTTP 模式重构**（v3.0.0）——把项目从 "stdio + 每 Agent 一进程一端口一浏览器 Tab" 改造为 "单守护进程 + HTTP MCP + 单浏览器页面聚合多会话"。

- 设计文档：[`docs/architecture/multi-session-http-redesign.md`](./docs/architecture/multi-session-http-redesign.md)
- 状态：**设计定稿**，所有决议事项已确认（见文档 §10），待进入阶段 1（后端多会话化）实施。
- 关键决策速览：
  - **破坏性变更**：v3.0 完全移除 stdio 模式，不保留兜底；用户手动改 `mcp.json`
  - 启动方式与当前一致（`uvx`/`pip` 手动命令），不提供 LaunchAgent/systemd
  - 固定端口 `127.0.0.1:8765`，冲突直接报错
  - 不启用 Token 鉴权（本地单用户场景）
  - 新增 `title` 可选参数作为会话标识；未传则用项目目录 basename 兜底
  - Tauri 桌面模式 v3.0 暂停维护（源码保留）
  - 仅考虑 Cursor IDE / Cursor CLI 使用场景

## 快速索引

| 目的 | 看这里 |
|---|---|
| 理解现有四层架构 | `docs/architecture/system-overview.md` |
| 了解当前多会话改造提案 | `docs/architecture/multi-session-http-redesign.md` |
| MCP tool / WebSocket API | `docs/architecture/api-reference.md` |
| 组件实现细节 | `docs/architecture/component-details.md` |
| 部署运维 | `docs/architecture/deployment-guide.md` |
| 版本历史 | `CHANGELOG.zh-CN.md` / `RELEASE_NOTES/` |

## 关键实现文件（对重构最相关）

- `src/mcp_feedback_enhanced/server.py` — MCP 入口、`interactive_feedback` tool
- `src/mcp_feedback_enhanced/web/main.py` — `WebUIManager` 单例（将大改）
- `src/mcp_feedback_enhanced/web/routes/main_routes.py` — FastAPI 路由、`/ws`
- `src/mcp_feedback_enhanced/web/models/feedback_session.py` — 会话状态机
- `src/mcp_feedback_enhanced/web/static/js/modules/websocket-manager.js` — 前端 WS
- `src/mcp_feedback_enhanced/web/static/js/modules/session/session-data-manager.js` — 前端会话数据
- `src/mcp_feedback_enhanced/__main__.py` — CLI（将新增 `serve --http`）

## 开发约定

- 文档语言：既有架构文档用**繁体中文**；新设计文档用**简体中文**（与开发者日常沟通一致）；UI 三语支持（zh-TW / zh-CN / en）
- 提交规范：参照 `.specify/memory/constitution.md`（若存在）及现有 commit 历史
- 测试入口：`uv run pytest`（详见 `tests/`）
