# Changelog (English)

This document records version updates for the **MCP Interactive Feedback
(HTTP fork)**. History below only covers this fork (from **v3.0.0** onwards).

Everything **v2.6.x and earlier** belongs to the upstream project
([Minidoracat/mcp-feedback-enhanced](https://github.com/Minidoracat/mcp-feedback-enhanced))
and is not tracked here.

---

## [v3.2.0] - 2026-04-27 - AI Conversation Timeline, Simplified State Flow & Connection Stability

### 🌟 Highlights
- AI summaries are now persisted as history; the frontend merges them with user
  messages into a chronological conversation timeline
- Session state flow simplified: skips the ACTIVE transitional state, going
  directly from WAITING to FEEDBACK_SUBMITTED
- "Last prompt" button replaced with "Last submission" — reuses the user's most
  recently submitted feedback text from the current session

### ✨ New Features
- 🕐 **AI summary history & conversation timeline**: backend stores historical
  AI summaries in an `ai_summaries` list; frontend merges AI summaries and user
  messages into a chronological timeline in the session details modal; session
  duration fixed with real timestamps; new i18n keys (`userLabel`,
  `timelineSummary`, `copyAll`); includes `inject_test_session.py` test script
- 🔄 **"Last submission" button**: the former "Last prompt" button no longer
  recalls saved prompt templates — it reuses the user's most recently submitted
  feedback text from the current session's `user_messages`

### ♻️ Refactoring
- ⚡ **Skip ACTIVE transitional state**: state flow simplified to WAITING →
  FEEDBACK_SUBMITTED; `submit_feedback()` calls `next_step()` once; sidebar
  "in progress" badge now counts `feedback_submitted` sessions
- 🧹 **Remove daemon PID lock**: dropped `DaemonPidLock` from `daemon.py`,
  `__main__.py`, and `utils/__init__.py`; removed `--pid-file` CLI argument;
  cleaned up PID-lock references across 12 doc files

### 🐛 Bug Fixes
- 🔄 **Restore currentSession on page refresh**: `loadFromServer` now sets
  `currentSession` from `/api/all-sessions` when empty after page refresh,
  fixing "no current session data" on the workspace copy button
- 🔌 **MCP connection logging & Ctrl+C shutdown**: moved new-client log into
  `send_wrapper` for SSE response interception; replaced `@app.middleware` with
  pure ASGI middleware to eliminate `CancelledError` on shutdown; switched to
  `uvicorn.error` logger; skipped compression for `/mcp` paths; increased
  `timeout_graceful_shutdown` to 2s
- 📝 **Markdown rendering lost on page refresh**: removed duplicate `setTimeout`
  re-render that overwrote correctly formatted content

---

## [v3.1.1] - 2026-04-25 - Smart Session Matching, Draft Isolation & Stability

### 🌟 Highlights
- Fallback session matching by `title` + `project_directory` when
  `feedback_session_id` is omitted; WAITING/ACTIVE status restriction removed
  so any session can be reused
- Reusing a WAITING session appends the new AI summary (separated by `---`)
  instead of replacing it, preserving the user's in-progress draft and images
- Switching sessions now saves/restores images per session — no more cross-session
  image leakage

### ✨ New Features
- 🔍 **Match sessions by title + project path**: server finds and reuses the
  most recent session with the same `title` and `project_directory`
- 🔄 **Status-agnostic session reuse**: all session states are reusable; WAITING
  sessions get summary appended with `---`, drafts and images preserved
- 📊 **MCP connect/disconnect INFO logs**: daemon logs new client connections
  and disconnections at INFO level

### 🐛 Bug Fixes
- 🛡️ **Compression middleware RuntimeError**: `call_next()` crash under
  concurrent HTTP + WebSocket traffic now caught with HTTP 500 fallback
- 🖼️ **Per-session image drafts**: switching sessions no longer shares images;
  each session independently saves/restores its draft images
- 📐 **Session details modal z-index**: raised from 2000 to 2200 so it renders
  above the session history modal
- 🔇 **Audio autoplay false positive**: page refresh no longer shows the
  "browser blocked autoplay" notification — only shown if autoplay fails after
  the user has already interacted with the page

### 📚 Documentation
- 📝 **Agent Skill subagent identity**: `SKILL.md` updated
- 📖 **API reference session reuse priority**: three-tier reuse logic documented

---

## [v3.1.0] - 2026-04-24 - Session Reuse & Agent Skill

### 🌟 Highlights
Same-conversation calls to `interactive_feedback` now reuse one browser
session instead of spawning a new card every turn. An Agent Skill ships in
the repo so any compatible agent automatically loops on user feedback.

### ✨ New Features
- 🔄 **`feedback_session_id` for session reuse**: the tool returns a
  `feedback_session_id` in its response; passing it back on subsequent calls
  reuses the same UI session — no new sidebar cards, feedback text is cleared
  and the AI summary is updated in place
- 📝 **Agent Skill (`skills/interactive-feedback-loop/`)**: open-standard
  `SKILL.md` that teaches any agent to call the tool after every task, extract
  and reuse `feedback_session_id`, retry on MCP timeout, and never call the
  tool from a subagent

### 🐛 Bug Fixes
- ✏️ **Feedback text preserved after submit**: input box now keeps the user's
  text after submission until the next AI summary arrives (instead of clearing
  it immediately)
- 📄 **Markdown renders on page refresh**: raw markdown injected by Jinja2 is
  rendered immediately on load, no longer requires a WebSocket snapshot event
- 🔁 **Session reuse condition fixed**: `FEEDBACK_SUBMITTED` sessions are now
  correctly treated as reusable (previously blocked by the `is_active` check)
- 🧹 **Feedback text clears on reuse**: when a session is reused
  (status → `waiting`), draft text, images, and the old summary are replaced
  synchronously via the Store listener, bypassing debounce timing issues
- ⏎ **Ctrl+C exits daemon immediately**: `timeout_graceful_shutdown=0`
  prevents the "Waiting for connections to close" hang on SIGINT

### 📚 Documentation
- 📖 **Agent Skill section in README** (en / zh-CN / zh-TW): installation
  instructions, feature list, and link to the shipped `SKILL.md`
- 📋 **CHANGELOG system & release workflow**: trilingual CHANGELOG files under
  `RELEASE_NOTES/`, GitHub Actions workflow for automated releases, and a
  `scripts/release.py` helper

---

## [v3.0.1] - 2026-04-24 - Workspace i18n & UI Refinements

### 🌟 Highlights
Trilingual polish of the v3.0 dual-pane UI: workspace strings are now fully
localized, README screenshots are regenerated in each language, and several
layout bugs in the combined workspace tab are fixed.

### 🐛 Bug Fixes
- 🌐 **Complete workspace i18n**: fixed remaining non-translated strings in the
  combined workspace tab and tightened non-CJK time formatting
- 🖼️ **Floating stats panel removed**: folded connection metrics into the
  status-bar tooltip so they no longer obscure the session history button
- 📐 **Adaptive AI summary height**: summary area now grows with content up to
  `min(58vh, 540px)` and no longer overflows the image attachment strip
- 🔄 **Layout switch is now live**: toggling horizontal/vertical layout in
  settings applies immediately (no page refresh needed)
- 🏷️ **Fixed zh-TW `app.title`**: was accidentally showing the English brand
- 📝 **Disambiguated copy button**: summary-header "copy user content" is now
  "copy all user messages" so it no longer collides with the prompt button

### 🎨 UI Refinements
- 🗂️ **Session history button**: minor restyle so it reads as an interactive
  control rather than a decorative label
- 🖼️ **Trilingual README screenshots**: `docs/{en,zh-CN,zh-TW}/images/` are
  regenerated against the current UI in each interface language

### 📚 Documentation
- 🔄 **README icons and wording**: synced with the v3.0.x 3-layer UI (topbar
  globals / sidebar history / session-only tabs)

---

## [v3.0.0] - 2026-04-23 - HTTP Daemon, Multi-Session, 3-Layer UI

### 🌟 Highlights
First release of the self-use fork. Drops stdio transport entirely in favor of
a single long-running HTTP daemon on `127.0.0.1:8765`, routes every
`interactive_feedback` call into one browser tab via WebSocket multiplexing,
and reorganizes the UI into a 3-layer information architecture.

### 💥 Breaking Changes
- 🚫 **stdio transport removed**: every AI agent on the machine must point its
  `mcp.json` at `http://127.0.0.1:8765/mcp/`; per-project `uvx` launchers are
  no longer supported
- 🖥️ **Tauri desktop shell paused**: no longer built or released; source kept
  under `src-tauri/` for reference only

### ✨ New Features
- 🌐 **HTTP daemon (Phases 1 + 2)**: `uv run mcp-interactive-feedback serve
  --http` starts one daemon per host; FastMCP Streamable HTTP is mounted at
  `/mcp/`; a PID lock prevents duplicate instances on the fixed port
- 🗂️ **Real multi-session (Phase 3 backend)**: concurrent
  `interactive_feedback` calls coexist — sessions are **inserted** into the
  registry instead of replacing the previous one
- 👁️ **Sticky active pointer**: incoming sessions do **not** steal your current
  view; users are notified only via sidebar red dot + `(N)` title prefix +
  favicon badge + OS notification
- 🖼️ **Dual-pane SPA (Phase 3 frontend)**: single browser tab with left
  session sidebar and right tabbed workspace; keyboard shortcut
  `Cmd/Ctrl + 1..9` jumps between sessions
- 📝 **Per-session draft state**: text feedback / images / commands are kept
  independently per session and restored on switch
- 🏷️ **`title` argument on the MCP tool**: optional — falls back to the
  project directory basename
- 🧱 **3-layer UI**: topbar hosts app-level actions (⚙️ settings, ℹ️ about),
  left sidebar bottom hosts 🗂️ session history, right pane tabs keep only
  session-level content (workspace with embedded AI summary / command)

### 🐛 Bug Fixes
- 🔁 **Cross-session feedback leak**: feedback submitted in session A no longer
  leaks into session B when switching focus mid-submit
- 🧹 **Session state machine**: `WebFeedbackSession` state transitions
  corrected and resource cleanup now guards against self-termination
- ⏱️ **Session card time is stable**: session list timestamps no longer
  reset on re-render; reconnect indicator reflects the actual socket state
- 📊 **Detailed stats panel values**: numbers in the detailed stats panel now
  match the backend registry after Phase 3 refactor

### 🎨 UI Refactor
- 🗺️ **3-layer information architecture**: topbar (app-global) / sidebar
  (session history) / tabs (session-scoped) replaced the old single-session
  navigation bar
- 📦 **AI summary embedded in workspace tab**: merged with the feedback editor
  to give both vertical and horizontal layout options

### 🏷️ Branding
- 🔀 **Renamed to "MCP Interactive Feedback (HTTP fork)"** — separate from
  upstream branding; Discord link and hardcoded upstream version strings
  removed; repository/PyPI URLs across configs now point at this fork

### 📚 Documentation
- 📐 **Architecture docs rewritten for v3.0**: HTTP daemon design,
  multi-session UI redesign notes, Phase 2/3 usage guides; upstream desktop
  build guides removed
- 🌍 **Trilingual README rewritten** (en / zh-CN / zh-TW) to describe the
  v3.0 HTTP daemon flow end-to-end

---
