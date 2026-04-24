# Changelog (English)

This document records version updates for the **MCP Interactive Feedback
(HTTP fork)**. History below only covers this fork (from **v3.0.0** onwards).

Everything **v2.6.x and earlier** belongs to the upstream project
([Minidoracat/mcp-feedback-enhanced](https://github.com/Minidoracat/mcp-feedback-enhanced))
and is not tracked here.

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
