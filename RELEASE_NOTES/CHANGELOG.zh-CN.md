# 更新日志 (简体中文)

本文件记录 **MCP Interactive Feedback（HTTP fork）** 的版本更新历史。
下方条目仅涵盖本 fork（从 **v3.0.0** 起算）。

所有 **v2.6.x 及之前**的版本都属于上游项目
[Minidoracat/mcp-feedback-enhanced](https://github.com/Minidoracat/mcp-feedback-enhanced)，
不在本 CHANGELOG 范围内。

---

## [v3.2.0] - 2026-04-27 - AI 对话时间线、状态流简化与连接稳定性

### 🌟 版本亮点
- AI 摘要历史持久化保存，前端将 AI 摘要与用户消息合并为按时间排列的对话时间线
- 会话状态流简化：跳过 ACTIVE 过渡态，WAITING 直接进入 FEEDBACK_SUBMITTED
- "上次提示"按钮改为"上次提交"，复用当前会话中用户最近提交的反馈文本

### ✨ 新功能
- 🕐 **AI 摘要历史与对话时间线**：后端将历次 AI 摘要保存在 `ai_summaries`
  列表中；前端在会话详情弹窗中将 AI 摘要与用户消息按时间合并为对话时间线；
  修正会话时长计算；新增 i18n key（`userLabel`、`timelineSummary`、`copyAll`）；
  附带 `inject_test_session.py` 测试脚本
- 🔄 **"上次提交"按钮**：原"上次提示"按钮不再回调已保存的提示词模板，
  改为复用当前会话中用户最近一条已提交的反馈文本

### ♻️ 重构
- ⚡ **跳过 ACTIVE 过渡态**：状态流简化为 WAITING → FEEDBACK_SUBMITTED；
  `submit_feedback()` 仅调用一次 `next_step()`；侧栏"进行中"徽章改为
  统计 `feedback_submitted` 状态的会话
- 🧹 **移除 daemon PID 锁单实例检测**：删除 `DaemonPidLock`、`--pid-file`
  CLI 参数，清理 12 个文档中的 PID 锁引用

### 🐛 问题修复
- 🔄 **页面刷新后恢复 currentSession**：`loadFromServer` 在页面刷新后从
  `/api/all-sessions` 恢复 `currentSession`，修复工作区复制按钮提示
  "无当前会话数据"
- 🔌 **MCP 连接日志与 Ctrl+C 关闭优化**：将新客户端日志移入 `send_wrapper`
  以拦截 SSE 响应；替换 `@app.middleware` 为纯 ASGI 中间件消除关闭时
  `CancelledError`；使用 `uvicorn.error` 日志器；`/mcp` 路径跳过压缩；
  `timeout_graceful_shutdown` 提升至 2s
- 📝 **页面刷新后 Markdown 渲染丢失**：移除重复的 `setTimeout` 重渲染逻辑，
  不再覆盖已正确格式化的内容

---

## [v3.1.1] - 2026-04-25 - 会话智能匹配、草稿隔离与稳定性修复

### 🌟 版本亮点
- 新增依 `title` + `project_directory` 的会话自动匹配（`feedback_session_id`
  的兜底逻辑）；移除 WAITING/ACTIVE 状态限制，允许任何状态的 session 被复用
- WAITING 状态下复用 session 时 AI 摘要以分隔线追加（不覆盖），同时保留
  用户正在编辑的草稿文本与图片
- 切换会话时图片草稿按会话独立保存/恢复，不再跨会话共享

### ✨ 新功能
- 🔍 **按标题 + 项目路径匹配会话**：当 `feedback_session_id` 未提供时，
  服务端查找 `title` 和 `project_directory` 一致的最近会话并复用
- 🔄 **移除会话复用状态限制**：所有状态的 session 均可被复用；WAITING
  状态下 AI 摘要以 `---` 分隔线追加，草稿文本和图片不被清空
- 📊 **MCP 连接/断开 INFO 日志**：daemon 日志中打印新客户端连接与断开事件

### 🐛 问题修复
- 🛡️ **压缩中间件 RuntimeError**：`call_next()` 并发场景下的
  `RuntimeError: No response returned` 现在捕获并回退到 HTTP 500
- 🖼️ **图片草稿按会话隔离**：切换会话时图片不再共享，每个会话独立保存
- 📐 **会话详情弹窗 z-index**：从 2000 提升到 2200，不再被会话历史遮挡
- 🔇 **音效自动播放误报**：页面刷新后不再弹出"浏览器阻止音效"提示——仅在
  用户交互后仍被阻止时才显示通知

### 📚 文档
- 📝 **Agent Skill 子代理身份提示**：`SKILL.md` 新增说明
- 📖 **API 参考会话复用优先级**：文档化三级复用逻辑

---

## [v3.1.0] - 2026-04-24 - 会话复用与 Agent Skill

### 🌟 版本亮点
同一对话内多次调用 `interactive_feedback` 现在会复用同一个浏览器会话，
不再每轮都创建新卡片。仓库附带 Agent Skill，让任何兼容的 AI Agent
都能自动循环收集用户反馈。

### ✨ 新功能
- 🔄 **`feedback_session_id` 会话复用**：工具返回的 `feedback_session_id`
  传入下一次调用即可复用同一 UI 会话——不会产生新侧栏卡片，反馈文本被清空，
  AI 摘要就地更新
- 📝 **Agent Skill (`skills/interactive-feedback-loop/`)**：符合开放标准的
  `SKILL.md`，教 Agent 在每次任务后调用工具、提取并复用
  `feedback_session_id`、超时重试、禁止子代理调用

### 🐛 问题修复
- ✏️ **提交后保留反馈文本**：输入框在提交后不再立即清空，等到下一轮 AI
  摘要到来时才清空
- 📄 **页面刷新后 Markdown 正常渲染**：Jinja2 注入的原始 Markdown 在页面加载时
  立即渲染，不再依赖 WebSocket 快照事件
- 🔁 **会话复用条件修正**：`FEEDBACK_SUBMITTED` 状态的会话现在能被正确复用
  （之前被 `is_active` 检查阻断）
- 🧹 **复用时清空反馈文本**：当会话被复用（状态回到 `waiting`）时，草稿文本、
  图片和旧摘要通过 Store 监听器同步替换，绕过了 debounce 时序问题
- ⏎ **Ctrl+C 立即退出 daemon**：设置 `timeout_graceful_shutdown=0`，
  不再出现"等待连接关闭"的挂起

### 📚 文档
- 📖 **README 新增 Agent Skill 章节**（en / zh-CN / zh-TW）：安装说明、
  功能列表，以及指向 `SKILL.md` 的链接
- 📋 **CHANGELOG 系统与发布工作流**：`RELEASE_NOTES/` 下三语 CHANGELOG 文件，
  GitHub Actions 自动发布工作流，以及 `scripts/release.py` 辅助脚本

---

## [v3.0.1] - 2026-04-24 - 工作区 i18n 与 UI 细节打磨

### 🌟 版本亮点
对 v3.0 双栏 UI 的三语本地化打磨：工作区字符串全面国际化，三套 README
截图按对应界面语言重新生成，组合工作区选项卡中的若干布局问题一起修掉。

### 🐛 问题修复
- 🌐 **工作区完整 i18n**：修补组合工作区选项卡里遗留的未翻译字符串，并收紧
  非 CJK 时区下的时间格式
- 🖼️ **移除悬浮统计面板**：将连接指标折入状态栏 tooltip，不再遮挡会话历史按钮
- 📐 **AI 摘要自适应高度**：摘要区现在会随内容伸展到 `min(58vh, 540px)`，
  也不再溢出到图片附件条
- 🔄 **布局切换实时生效**：设置中切换横/竖布局立即生效，无需刷新页面
- 🏷️ **修复 zh-TW `app.title`**：此前误显示英文品牌名
- 📝 **复制按钮去歧义**：摘要头部的"复制用户内容"改为"复制所有用户消息"，
  不再与提示词按钮冲突

### 🎨 界面细节
- 🗂️ **会话历史按钮**：轻量重绘，让它一眼就像可点控件，而不像装饰文字
- 🖼️ **三语 README 截图**：`docs/{en,zh-CN,zh-TW}/images/` 按对应界面语言
  在当前 UI 下重新生成

### 📚 文档
- 🔄 **README 图标与措辞**：与 v3.0.x 的 3 层 UI（顶栏全局 / 侧栏会话历史
  / 右栏会话级 Tab）保持一致

---

## [v3.0.0] - 2026-04-23 - HTTP Daemon、多会话、3 层 UI

### 🌟 版本亮点
自用分支的首个正式版本。彻底移除 stdio，改为单机一个常驻 HTTP daemon
（`127.0.0.1:8765`），所有 `interactive_feedback` 调用经 WebSocket 多路复用
汇入同一浏览器页面；UI 也重构成 3 层信息架构。

### 💥 破坏性变更
- 🚫 **移除 stdio 传输**：所有 AI Agent 的 `mcp.json` 都必须指向
  `http://127.0.0.1:8765/mcp/`，不再支持按项目 `uvx` 启动
- 🖥️ **Tauri 桌面外壳暂停维护**：不再构建与发布；源码保留在 `src-tauri/`
  仅作参考

### ✨ 新功能
- 🌐 **HTTP daemon（Phase 1+2）**：`uv run mcp-interactive-feedback serve
  --http` 在单机启一个常驻 daemon；FastMCP Streamable HTTP 挂在 `/mcp/`
  下；固定端口 + PID 锁防止多实例
- 🗂️ **真正的多会话（Phase 3 后端）**：并发的 `interactive_feedback` 调用
  会**插入**到会话注册表，不再覆盖上一个会话
- 👁️ **粘滞活跃指针**：新会话到达**不会**抢走当前视图，只通过侧栏红点 +
  `(N)` 标题前缀 + Favicon 徽章 + 系统通知 四层提示用户
- 🖼️ **双栏 SPA（Phase 3 前端）**：单浏览器页面，左侧会话侧栏 + 右侧 Tab
  化工作区；`Cmd/Ctrl + 1..9` 快捷跳转会话
- 📝 **逐会话草稿状态**：文字反馈 / 图片 / 命令行按会话独立保存，切换会话时还原
- 🏷️ **MCP 工具新增 `title` 可选参数**：缺省时用项目目录名
- 🧱 **3 层 UI 架构**：顶栏放应用级动作（⚙️ 设定 / ℹ️ 关于），左栏底部放
  🗂️ 会话历史，右栏 Tab 仅保留会话级内容（工作区含嵌入的 AI 摘要 / 命令）

### 🐛 问题修复
- 🔁 **跨会话反馈泄露**：在会话 A 提交反馈时切到会话 B，不会再把反馈错投到 B
- 🧹 **会话状态机**：修正 `WebFeedbackSession` 的状态转移；资源清理时
  防止对自身重复终止
- ⏱️ **会话卡时间稳定**：会话列表的时间戳不再在每次重渲染时重置；重连
  指示灯反映真实 socket 状态
- 📊 **详细统计面板数值**：Phase 3 重构后详细统计面板的数字与后端注册表一致

### 🎨 UI 重构
- 🗺️ **3 层信息架构**：顶栏（应用级）/ 侧栏（会话历史）/ Tab（会话级）取代
  老的单会话导航条
- 📦 **AI 摘要嵌入工作区 Tab**：与反馈编辑器合并，支持横向/纵向两种布局

### 🏷️ 品牌
- 🔀 **更名为 "MCP Interactive Feedback (HTTP fork)"**：与上游品牌切分；
  移除 Discord 链接和硬编码的上游版本号；配置中的仓库/PyPI URL 全部指向本 fork

### 📚 文档
- 📐 **架构文档按 v3.0 重写**：HTTP daemon 设计、多会话 UI 重构笔记、
  Phase 2/3 使用指南；删除上游的桌面构建指南
- 🌍 **三语 README 重写**（en / zh-CN / zh-TW）：完整覆盖 v3.0 HTTP daemon
  的使用链路

---
