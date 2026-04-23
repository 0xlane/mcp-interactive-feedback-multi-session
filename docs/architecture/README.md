# MCP Feedback Enhanced 架構文檔

> **v3.0 已落地**：單守護進程 + HTTP + 多會話 + 單浏览器視圖。
> 若你是第一次來看這個倉庫，請從下表的「v3.0 推薦讀物」開始。
> 關於 v2.x 向 v3.0 的遷移背景、設計取捨與 lessons learned，單獨
> 記錄在 [`multi-session-http-redesign.md`](./multi-session-http-redesign.md)。

## 📋 文檔索引

| 文檔 | 描述 | 適用對象 |
| --- | --- | --- |
| [系統架構總覽](./system-overview.md) ⭐ | v3.0 拓撲、四層架構、與 v2.x 差異 | 所有人 |
| [組件詳細說明](./component-details.md) | 後端模組責任 + 前端模組地圖 | 開發 / 維護 |
| [交互流程](./interaction-flows.md) | Daemon 啟動、MCP 調用、切會話、提交、歸檔等序列圖 | 集成 / 調試 |
| [API 參考](./api-reference.md) | MCP 工具、REST、WebSocket、會話摘要對象 | API 使用者 / 前端 |
| [部署指南](./deployment-guide.md) | 本地、SSH 遠程、launchctl / systemd、升級回滾 | 運維 / 使用者 |
| [多會話 HTTP 重構設計](./multi-session-http-redesign.md) | 設計背景、影響矩陣、阶段路線、Phase 3 落地差異 | 架構師、核心開發 |
| [Phase 2：HTTP Daemon 使用指南](./phase2-http-daemon-usage.md) | `serve --http` 啟動、`mcp.json` 改造、端點清單 | 早期使用者 |
| [Phase 3：雙欄多會話 UI 使用指南](./phase3-multi-session-ui-usage.md) | 雙欄 UI、快捷鍵、草稿、粘滯 active、歸檔語義 | 日常使用者、前端維護 |

---

## 🏗️ 架構概覽

v3.0 以三句話講完：

1. **單機一個 daemon**：`uvx mcp-feedback-enhanced serve --http` 常駐，
   綁定 127.0.0.1:8765（可自定）。
2. **多會話並存**：每次 MCP `interactive_feedback` 調用插入一個
   `WebFeedbackSession`，互不銷毀。
3. **單瀏覽器聚合**：一個 SPA 頁面連 `/ws` 多路復用 WebSocket，
   所有會話在側欄列出、點擊或 `Cmd/Ctrl+1..9` 切換。

更細節的圖和字段請看 [`system-overview.md`](./system-overview.md)。

### 核心特性

- **多會話並存**（插入式 `create_session`，不再銷毀舊會話）
- **粘滯活躍指針**（新會話不抢前端視圖，由使用者顯式切換）
- **單 WebSocket 多路复用**（事件以 `session_id` 路由）
- **每會話獨立草稿**（切會話不丟輸入）
- **Title `(N)` / Favicon 紅點 / 系統通知 / `Cmd/Ctrl+1..9`**
- **歸檔 = 物理刪除**（刷新不會復活已歸檔會話）
- **PID 鎖 + 顯式固定端口**（多 Agent 安全共享同一 daemon）
- **三語 i18n**（zh-TW / zh-CN / en）
- **3 層資訊架構**（頂欄 = ⚙️ 設定 / ℹ️ 關於；左欄底部 = 📊 會話歷史；右欄 Tab = 會話級工作區 / AI 摘要 / 命令；參見 [Phase 3 使用指南 §3](./phase3-multi-session-ui-usage.md)）

### 技術棧

- **後端**: Python 3.11+, FastMCP（Streamable HTTP）, FastAPI, uvicorn
- **前端**: ES modules, 原生 WebSocket, Canvas, Notification API
- **工具**: `uv` / `uvx`, `pytest` + `pytest-asyncio`, `ruff`, `mypy`
- **發布**: PyPI（見 [`../WORKFLOWS.md`](../WORKFLOWS.md)；Tauri 桌面
  構建已暫停）

---

## 🎯 快速導航

- **我要先把它跑起來** → [部署指南](./deployment-guide.md)
- **我要讓 Agent 連過來** → [API 參考 §1 + §2](./api-reference.md#1-mcp-工具)
- **我要在瀏覽器裡用它** → [Phase 3 UI 使用指南](./phase3-multi-session-ui-usage.md)
- **我要改後端** → [組件詳細說明](./component-details.md) + [重構設計](./multi-session-http-redesign.md)
- **我要改前端** → [組件詳細說明 §8](./component-details.md#8-前端模块地图)
- **我要接 API** → [API 參考](./api-reference.md)
- **SSH 遠端** → [`../en/ssh-remote/browser-launch-issues.md`](../en/ssh-remote/browser-launch-issues.md)（含 zh-CN / zh-TW）
- **桌面模式 / CI 發布** → [`../WORKFLOWS.md`](../WORKFLOWS.md)

---

## 🧭 文檔狀態

所有主要架構文檔均已針對 **v3.0** 重寫。若你在舊分支或歷史提交裡看
到 v2.x 版本的同名文檔，以本目錄當前 `HEAD` 為準。

---

**當前版本**: v3.0.0-dev
**最後更新**: 2026-04-23
**架構類型**: 單 Daemon + FastAPI + FastMCP HTTP + 雙欄 SPA 多會話 UI（3 層資訊架構：頂欄應用動作 · 左欄會話列表 · 右欄會話級 Tab）
