# 更新日誌 (繁體中文)

本文件記錄 **MCP Interactive Feedback（HTTP fork）** 的版本更新歷史。
下方條目僅涵蓋本 fork（從 **v3.0.0** 起算）。

所有 **v2.6.x 以及之前**的版本都屬於上游專案
[Minidoracat/mcp-feedback-enhanced](https://github.com/Minidoracat/mcp-feedback-enhanced)，
不在本 CHANGELOG 範圍內。

---

## [v3.1.1] - 2026-04-25 - 會話智能匹配與穩定性修復

### 🌟 版本亮點
新增依 `title` + `project_directory` 的會話自動匹配機制，作為
`feedback_session_id` 的兜底邏輯：即使 Agent 忘記傳回 session ID，
服務端也能根據標題與專案路徑找到已有會話並復用。同時修復了中介軟體
在並發 HTTP/WebSocket 場景下的崩潰問題。

### ✨ 新功能
- 🔍 **按標題 + 專案路徑匹配會話**：當 `feedback_session_id` 未提供時，
  服務端會在現有已完成 / 已提交的會話中查找 `title` 和 `project_directory`
  都一致的最近一個，自動復用——避免 Agent 遺漏 ID 時建立多餘卡片

### 🐛 問題修復
- 🛡️ **壓縮中介軟體 RuntimeError**：`compression_and_cache_middleware` 中
  `call_next()` 在並發 HTTP + WebSocket 請求下可能拋出
  `RuntimeError: No response returned`（Starlette 1.0.0 已知問題），
  現在捕獲並回退到 HTTP 500 回應，不再造成 daemon 崩潰

### 📚 文件
- 📝 **Agent Skill 子代理身份提示**：`SKILL.md` 新增說明，要求頂層 Agent
  在建立子代理（Task tool）時明確標注子代理身份，禁止子代理呼叫
  `interactive_feedback`

---

## [v3.1.0] - 2026-04-24 - 會話復用與 Agent Skill

### 🌟 版本亮點
同一對話內多次呼叫 `interactive_feedback` 現在會復用同一個瀏覽器會話，
不再每輪都建立新卡片。倉庫附帶 Agent Skill，讓任何相容的 AI Agent
都能自動循環收集使用者回饋。

### ✨ 新功能
- 🔄 **`feedback_session_id` 會話復用**：工具回傳的 `feedback_session_id`
  傳入下一次呼叫即可復用同一 UI 會話——不會產生新側欄卡片，回饋文字被清空，
  AI 摘要就地更新
- 📝 **Agent Skill (`skills/interactive-feedback-loop/`)**：符合開放標準的
  `SKILL.md`，教 Agent 在每次任務後呼叫工具、擷取並復用
  `feedback_session_id`、逾時重試、禁止子代理呼叫

### 🐛 問題修復
- ✏️ **送出後保留回饋文字**：輸入框在送出後不再立即清空，等到下一輪 AI
  摘要到來時才清空
- 📄 **頁面重整後 Markdown 正常渲染**：Jinja2 注入的原始 Markdown 在頁面載入時
  立即渲染，不再依賴 WebSocket 快照事件
- 🔁 **會話復用條件修正**：`FEEDBACK_SUBMITTED` 狀態的會話現在能被正確復用
  （此前被 `is_active` 檢查阻斷）
- 🧹 **復用時清空回饋文字**：當會話被復用（狀態回到 `waiting`）時，草稿文字、
  圖片和舊摘要透過 Store 監聽器同步替換，繞過了 debounce 時序問題
- ⏎ **Ctrl+C 立即結束 daemon**：設定 `timeout_graceful_shutdown=0`，
  不再出現「等待連線關閉」的卡住

### 📚 文件
- 📖 **README 新增 Agent Skill 章節**（en / zh-CN / zh-TW）：安裝說明、
  功能列表，以及指向 `SKILL.md` 的連結
- 📋 **CHANGELOG 系統與發佈工作流**：`RELEASE_NOTES/` 下三語 CHANGELOG 檔案，
  GitHub Actions 自動發佈工作流，以及 `scripts/release.py` 輔助腳本

---

## [v3.0.1] - 2026-04-24 - 工作區 i18n 與 UI 細節打磨

### 🌟 版本亮點
對 v3.0 雙欄 UI 的三語在地化打磨：工作區字串全面國際化，三套 README
截圖依對應介面語言重新產生，組合工作區分頁中的若干排版問題一起修掉。

### 🐛 問題修復
- 🌐 **工作區完整 i18n**：修補組合工作區分頁裡遺漏的未翻譯字串，並收緊
  非 CJK 時區下的時間格式
- 🖼️ **移除浮動統計面板**：將連線指標折入狀態列 tooltip，不再遮擋會話歷史按鈕
- 📐 **AI 摘要自適應高度**：摘要區現在會隨內容伸展到 `min(58vh, 540px)`，
  也不再溢出到圖片附件列
- 🔄 **版面切換即時生效**：設定中切換橫/直版面立即生效，不需刷新頁面
- 🏷️ **修復 zh-TW `app.title`**：此前誤顯示英文品牌名稱
- 📝 **複製按鈕去歧義**：摘要標頭的「複製使用者內容」改為「複製所有使用者訊息」，
  不再與提示詞按鈕衝突

### 🎨 介面細節
- 🗂️ **會話歷史按鈕**：輕量重繪，讓它一眼看起來就像可點控制項，而非裝飾文字
- 🖼️ **三語 README 截圖**：`docs/{en,zh-CN,zh-TW}/images/` 依對應介面語言
  在當前 UI 下重新產生

### 📚 文件
- 🔄 **README 圖示與措辭**：與 v3.0.x 的 3 層 UI（頂欄全域 / 側欄會話歷史
  / 右欄會話級分頁）保持一致

---

## [v3.0.0] - 2026-04-23 - HTTP Daemon、多會話、3 層 UI

### 🌟 版本亮點
自用分支的首個正式版本。徹底移除 stdio，改為單機一個常駐 HTTP daemon
（`127.0.0.1:8765`），所有 `interactive_feedback` 呼叫經 WebSocket 多路復用
匯入同一個瀏覽器頁面；UI 也重構成 3 層資訊架構。

### 💥 破壞性變更
- 🚫 **移除 stdio 傳輸**：所有 AI Agent 的 `mcp.json` 都必須指向
  `http://127.0.0.1:8765/mcp/`，不再支援按專案 `uvx` 啟動
- 🖥️ **Tauri 桌面外殼暫停維護**：不再建置與發佈；原始碼保留在 `src-tauri/`
  僅作參考

### ✨ 新功能
- 🌐 **HTTP daemon（Phase 1+2）**：`uv run mcp-interactive-feedback serve
  --http` 在單機啟一個常駐 daemon；FastMCP Streamable HTTP 掛在 `/mcp/`
  底下；固定埠 + PID 鎖防止多實例
- 🗂️ **真正的多會話（Phase 3 後端）**：併發的 `interactive_feedback` 呼叫
  會**插入**到會話註冊表，不再覆寫前一個會話
- 👁️ **黏滯活躍指標**：新會話到達**不會**搶走當前視圖，只透過側欄紅點 +
  `(N)` 標題前綴 + Favicon 徽章 + 系統通知 四層提示使用者
- 🖼️ **雙欄 SPA（Phase 3 前端）**：單瀏覽器頁面，左側會話側欄 + 右側分頁化
  工作區；`Cmd/Ctrl + 1..9` 快捷鍵跳轉會話
- 📝 **逐會話草稿狀態**：文字回饋 / 圖片 / 命令列按會話獨立保存，切換會話時還原
- 🏷️ **MCP 工具新增 `title` 可選參數**：未提供時以專案目錄名稱為預設
- 🧱 **3 層 UI 架構**：頂欄放應用級動作（⚙️ 設定 / ℹ️ 關於），左欄底部放
  🗂️ 會話歷史，右欄分頁僅保留會話級內容（工作區含嵌入的 AI 摘要 / 命令）

### 🐛 問題修復
- 🔁 **跨會話回饋外洩**：在會話 A 送出回饋時切到會話 B，不會再把回饋誤投到 B
- 🧹 **會話狀態機**：修正 `WebFeedbackSession` 的狀態轉移；資源清理時
  防止對自身重複終止
- ⏱️ **會話卡時間穩定**：會話列表的時間戳不再在每次重繪時重置；重連
  指示燈反映真實 socket 狀態
- 📊 **詳細統計面板數值**：Phase 3 重構後詳細統計面板的數字與後端註冊表一致

### 🎨 UI 重構
- 🗺️ **3 層資訊架構**：頂欄（應用級）/ 側欄（會話歷史）/ 分頁（會話級）取代
  舊的單會話導覽列
- 📦 **AI 摘要嵌入工作區分頁**：與回饋編輯器合併，支援橫向/縱向兩種版面

### 🏷️ 品牌
- 🔀 **更名為 "MCP Interactive Feedback (HTTP fork)"**：與上游品牌切分；
  移除 Discord 連結與硬編碼的上游版本字串；設定中的儲存庫/PyPI URL 全部指向本 fork

### 📚 文件
- 📐 **架構文件依 v3.0 重寫**：HTTP daemon 設計、多會話 UI 重構筆記、
  Phase 2/3 使用指南；刪除上游的桌面建置指南
- 🌍 **三語 README 重寫**（en / zh-CN / zh-TW）：完整覆蓋 v3.0 HTTP daemon
  的使用鏈路

---
