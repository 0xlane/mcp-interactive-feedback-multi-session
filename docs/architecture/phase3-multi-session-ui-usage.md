# 阶段 3：双栏多会话 UI 使用指南

> **状态**：阶段 3 已落地，本文档给出日常使用者 + 开发者可立即上手的路径。
> **前置依赖**：阶段 2 的 HTTP Daemon 已经跑起来（参见
> [phase2-http-daemon-usage.md](./phase2-http-daemon-usage.md)）。
> **面向对象**：Cursor IDE / Cursor CLI 用户；在本地同时跑多个 AI 会话
> 的开发者；参与 Phase 4+ 开发的核心贡献者。

## 1. Phase 3 解决了什么

阶段 1 / 2 已经把后端改成了「单 daemon 多会话」，但 UI 这一侧仍是单
活跃视图：每来一个新会话，浏览器 Tab 会被挤掉重新渲染成最新会话，
旧会话虽然在后端活着却看不到。

阶段 3 给用户的最直接体验：

- **一个浏览器 Tab 同时展现所有并发的 `interactive_feedback` 请求**，
  左侧会话侧栏、右侧当前会话详情；
- 切换会话**不会丢草稿**——每个会话独立的 textarea 内容；
- 有新会话进来时**不会把你从当前会话切走**，而是在侧栏打红点 +
  标题 `(N)` 前缀 + （如果授权）浏览器系统通知；
- `Cmd/Ctrl + 1..9` 按侧栏顺序秒切会话；
- 把一个会话归档（X 按钮）就是「真从后端字典删掉」——刷新页面、
  切换语言都不会让它重新冒出来。

## 2. 启动流程（与 Phase 2 一致）

```bash
# 一次性启动 daemon（保持前台）
uvx mcp-feedback-enhanced serve --http
# 或从源码
uv run python -m mcp_feedback_enhanced serve --http
```

浏览器访问 `http://127.0.0.1:8765/`。这次打开的不是空白等待页，而是
阶段 3 的 SPA 壳：没有会话时显示空态占位；一旦有 MCP 调用，侧栏立刻
出现新卡片，且**只有**你当前没在看任何会话时才会自动把它作为活跃。

> 首次打开浏览器若要启用「桌面通知」（当页面处于后台时弹出系统通
> 知），在任意交互里让浏览器请求 `Notification.requestPermission()`
> —— 代码里 `notify-badge.js` 会在用户授权后自动用。

## 3. 界面导览

### 3.1 侧栏（左）

```
┌───── 侧栏 ─────────┐
│ 📋 会话 · 3         │
│ [清除已完成]        │
├─────────────────────┤
│ ● backend-refactor  │  ← 最近创建（WAITING, 脉动动画）
│   8s • 修复登录重定向 │
│   [X]               │
│                     │
│ ● frontend-fix      │  ← 你正在看的这个（底色高亮）
│   1m • API 文档补全 │
│   [X]               │
│                     │
│ ○ api-validator     │  ← 已提交，橙色实心
│   3m • 补测试       │
│   [X]               │
│                     │
│ ✓ fixtures-update   │  ← 已完成/已取消，灰色
│   5m                │
│   [X]               │
└─────────────────────┘
```

卡片要素：
- **主文**：`title`（Agent 在 `interactive_feedback(title="...")`
  里传入）→ `summary` 截断 40 字 → `session_id` 前 8 位，依次兜底；
- **副文**：相对时间 + summary 尾部；
- **状态点**：红色脉动=WAITING、绿色实心=ACTIVE、橙色实心=已提交、
  灰色=终态；
- **pending 小红点**：新会话到达时你不在看它，它会挂一个红点；点开
  即消失；
- **右上角 [X]**：该会话归档按钮（见 §7）。

点击任何卡片会：
1. 本地切换右栏内容；
2. 保存当前右栏 textarea 草稿到前端 `_drafts[previousSessionId]`；
3. 读取目标会话的 `_drafts[targetSessionId]` 恢复到 textarea；
4. 发 WebSocket `set_active_session` 消息告诉后端「用户现在看的是
   `targetSessionId`」，后端同步 `_active_session_id`，这样
   `/api/current-session` 等接口和 `sessions_snapshot` 里的
   `is_current` 字段都跟上用户视角。

### 3.2 折叠 / 展开

- 侧栏顶部的 `‹` / `›` 图标切换折叠状态；
- 折叠状态会存在 `localStorage["mcp.sidebar.collapsed"]`，刷新后保留。

### 3.3 详情（右）

右栏就是原来 `feedback.html` 的那套 UI（项目路径、summary、输入、
图片上传、命令执行、提交按钮）。Phase 3 的区别：

| 场景 | 表单状态 |
|---|---|
| 没有任何活跃会话 | 显示空态占位卡片 + 表单整体禁用 |
| 查看 WAITING 会话 | 正常可输入可提交 |
| 查看 ACTIVE 会话 | 同上 |
| 查看 `FEEDBACK_SUBMITTED` | textarea 只读、提交按钮显示「已提交」 |
| 查看终态 (COMPLETED / CANCELED / TIMEOUT / EXPIRED / ERROR) | 全部只读，按钮禁用 |

状态流转自动刷新：你正在看一个 WAITING 会话，提交之后右栏自动变成
「已提交」态，不需要手动点别的。

## 4. 键盘快捷键

| 快捷键 | 行为 |
|---|---|
| `Cmd/Ctrl + 1..9` | 跳到侧栏第 N 个会话（按**创建时间降序**，和侧栏视觉顺序一致） |
| `Cmd/Ctrl + Enter` | 提交当前会话（仍在右栏 textarea 里） |
| 点击任意侧栏卡片 | 切换活跃会话 |

> 早期实现按后端字典插入顺序编号，结果侧栏第 1 位是 A 但
> `Cmd+1` 跳到 B，非常反直觉。现在严格按 `created_at` 降序。

## 5. 粘滞活跃指针（sticky-active pointer）

阶段 3 做了一个**行为层**的关键决定：**新会话到达不会把你当前的视图
切走**。

具体语义：

- `WebUIManager.create_session`：只有在「当前无活跃」或「活跃指针
  失效」时，才把新会话自动设为活跃；否则保留原活跃；
- 前端拿到 `session_created` WebSocket 事件时：如果你当前正在看另
  一个会话，新会话在侧栏打 `has_pending_notification = true`（红点
  + 脉动），但**不**替换右栏内容；
- 要看新会话，请自己点侧栏卡片或用 `Cmd+1`。

为什么这样：一个人面前一次只看一个任务；AI 并发给你塞 5 个反馈请求
的时候，你正在敲着 Session 3 的回复，结果被强行切到 Session 5，
既丢光草稿又打断思路，体验很差。

**坑位提醒**（给开发者）：任何在后端拿「新创建的那个 session」的地方，
**不能**用 `manager.get_current_session()`，要用
`manager.get_session(session_id)`。前者在粘滞语义下返回的是旧活跃。
这个坑已经被 `launch_web_feedback_ui` 踩过：Session B 的
`wait_for_feedback` 实际在等 Session A 的 `feedback_completed`，
结果用户提交 A 的反馈后，A / B 两个 agent 拿到同一份数据
（「跨会话串线」bug）。修复在
`src/mcp_feedback_enhanced/web/main.py`，回归测试
`tests/unit/test_multi_session.py::test_session_lookup_by_id_after_sticky_active`。

## 6. Pending 通知（四层）

从弱到强：

1. **侧栏红点 + 脉动**：默认开，永远会有；
2. **`document.title = "(N) MCP Feedback"`**：N 为「状态为 waiting
   且 `has_pending_notification = true` 的会话数」。`notify-badge.js`
   用 `MutationObserver` 监视 `<title>`，其他代码（比如
   `refreshPageContent`）把标题改成别的时，它会重新套上 `(N)`
   前缀，不会被抹掉；
3. **Favicon 动态红点**：Canvas 画 16×16 favicon，右上角盖红点，
   页面激活后自动消；
4. **浏览器桌面通知**：仅当用户授权过 `Notification.permission`
   且页面处于不可见状态时触发；每个 session_id 只通知一次，避免
   重复弹。

当前**没有**声音通知（`audio-manager.js` 仍在，但没接到 Phase 3 的
事件流上，避免默认就响打扰用户；未来可以做一个开关）。

## 7. 归档与清除

每张卡片右上角的 `[X]` 按钮是归档。注意 Phase 3 的归档语义**不是
UI 隐藏**，是**后端真的从字典移除**：

| 归档时的会话状态 | 行为 |
|---|---|
| WAITING / ACTIVE（MCP tool 还在 `wait_for_feedback`） | 后端 `session.cancel()` 解锁 `feedback_completed`，MCP tool 返回「用户取消了反馈」；会话从 `self.sessions` 字典 pop；侧栏卡片消失 |
| FEEDBACK_SUBMITTED（用户已提交但 MCP 还没取走） | 同步 `session.cleanup()` + 字典 pop。MCP 那边返回前的提交结果已经写在 `feedback_result` 里，不受影响 |
| 终态（COMPLETED / TIMEOUT / EXPIRED / CANCELED / ERROR） | 纯清理：同步 `cleanup()` + 字典 pop |

侧栏顶部的「**清除已完成**」按钮：批量归档所有终态会话（底层调用的是
`DELETE /api/sessions?status=completed` 加上 `all_terminal=true` 选项）。

**为什么不是 UI 隐藏**：早期尝试过「归档仅标记 UI 隐藏，保留后端
记录」，结果你清完一波完成的会话，刷新一下页面，`sessions_snapshot`
又把它们全推回来了，用户体验非常诡异。Phase 3 直接让归档成为「最终
状态」——需要回看历史请去 `session_history.json`（阶段 4/5 做
前端翻页）。

## 8. 开发辅助

### 8.1 在无 Cursor 的环境里模拟 MCP 调用

`scripts/dev_sim_feedback.py` 用真实 MCP HTTP transport 向
`http://127.0.0.1:8765/mcp/` 发起 `interactive_feedback` 调用，拿到
反馈后打印返回。

```bash
# 基本用法：启一个 session，等用户在浏览器里提交
uv run python scripts/dev_sim_feedback.py \
    --project /tmp \
    --summary "测试摘要：请检查这段代码" \
    --title "sample-task" \
    --timeout 600

# 并发测试粘滞语义：两个终端分别开 A / B
uv run python scripts/dev_sim_feedback.py --title sample-A --timeout 1800 &
uv run python scripts/dev_sim_feedback.py --title sample-B --timeout 1800 &

# 然后在浏览器里：
#   1. sample-A 会自动变活跃（因为 daemon 空启动时没别的 active）
#   2. sample-B 到达时只打 pending 红点，不切走 A
#   3. 切到 B，填反馈，提交 → 只有 sample-B 的脚本打印
#      "received feedback"，sample-A 继续 WAITING
```

`--timeout` 默认 1800 秒，手工操作时间足够；CI 里的集成测试用
`TestClient` 不走这个脚本。

### 8.2 手动触发活跃切换

浏览器 DevTools Console 里：

```javascript
// 切换到特定 session
MCPFeedback.sessionStore.setActiveSessionId('<session_id>', 'user');

// 查看当前 store 状态
MCPFeedback.sessionStore.getSessions();
MCPFeedback.sessionStore.getActiveSessionId();

// 重置 pending 标记（通常在点击卡片时自动做）
MCPFeedback.sessionStore.clearPending('<session_id>');
```

### 8.3 Cache buster

改完 `app.js` / `websocket-manager.js` / `session-sidebar.js` 等静态
文件之后，别忘了同步 bump `src/.../web/templates/feedback.html` 里对
应 `<script src="...?v=YYYYMMDDNN">` 的 `v=` 参数——已经启动 daemon
的用户如果不 bump 版本号，浏览器会拉旧缓存，看不到你的修改。

## 9. 已知限制 / 待办

| 项 | 状态 | 规划 |
|---|---|---|
| 侧栏折叠状态 `localStorage` 持久化 | ✅ 已做 | — |
| 归档二次确认弹窗（仅 WAITING/ACTIVE 会话） | ⏳ 未做 | 阶段 4 |
| 会话历史（超过保留期后的回看界面） | ⏳ 未做 | 阶段 4/5 |
| 音效通知 Phase 3 没接线 | ⏳ 未做 | 阶段 4/5 可选 |
| 桌面模式（Tauri） | 🚫 暂停维护 | 已在 §7 设计文档说明 |
| 归档 API 仅 WS 提交，无 REST | ⚠️ 部分 | `POST /api/sessions/{sid}/archive` 已有；前端目前走 WS |
| 多语言中英混排时 `(N)` 标题前缀偶尔在系统通知里被截断 | 🐞 极小 | 观察，不紧急 |
| 无声音 / 呼吸灯等被动通知（仅视觉 + 浏览器通知） | 🎛 体验权衡 | 默认不加强度，未来设置里加开关 |

## 10. 常见问题

**Q：我关掉浏览器 Tab 然后重新打开，会话还在吗？**
A：在的。Daemon 是独立进程，只要没关 daemon，`sessions` 字典里的
会话就一直活着。重新打开 Tab 会通过 `sessions_snapshot` 恢复全部
状态；但前端 `_drafts` 是页面内存，关 Tab 就没了——真要保护草稿，
记得先提交或复制出来。

**Q：我提交了反馈但 AI 没收到？**
A：第一步看 `http://127.0.0.1:8765/api/sessions` 里那条 session 的
`feedback_completed` 和 `status`。如果是 `feedback_submitted` 但
agent 没拿到，大概率 agent 侧的 `wait_for_feedback` 协程出了问题
（例如 Cursor Chat 被你手动中断过），而 daemon 已经把反馈存进
`feedback_result`；再发一次 `interactive_feedback` 重启会话即可。

**Q：为什么我看到会话 A 的反馈出现在会话 B 的 agent 那边？**
A：**不应该**。这是 Phase 3 开发期间踩过的 bug（见 §5 末尾），已经
有回归测试守护。如果你自己写的代码分支里出现这个症状，先 grep
`get_current_session()`—— 多半哪里用成了它而不是
`get_session(session_id)`。

**Q：`Cmd+1..9` 没反应？**
A：检查浏览器 / IME 有没有抢走这组快捷键。Mac 上 `Cmd+1..9` 在某些
IME 会被当成候选词选择；建议提交反馈时先关输入法焦点或先点一下右栏
输入框外的空白。

---

**相关文档**：
- [多会话 HTTP 模式重构设计](./multi-session-http-redesign.md)（总体设计 + 经验教训）
- [阶段 2 HTTP Daemon 使用指南](./phase2-http-daemon-usage.md)（daemon 启动与端点）
- [系统架构总览](./system-overview.md)（v3.0 前的单会话架构；升级后需更新）
