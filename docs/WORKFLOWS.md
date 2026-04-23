# GitHub Actions 工作流程說明（v3.0）

本項目使用 GitHub Actions 管理 CI / 發佈。v3.0 起停止維護桌面應用
構建路徑，僅保留 Web（HTTP daemon）發佈流。

## 🏗️ 現行工作流程

### `publish.yml` — PyPI 發佈

**用途**：版本管理 + PyPI 發佈 + GitHub Release

**觸發條件**：手動觸發（`workflow_dispatch`）

**功能**：
- 自動或手動版本號管理（patch / minor / major 或自訂版本）；
- 發佈到 PyPI；
- 創建 GitHub Release。

**使用方式**：

1. 前往 GitHub Actions → "Auto Release to PyPI"；
2. 點擊 "Run workflow"；
3. 選擇版本類型或輸入自訂版本。

## 🚫 已暫停的工作流程

### `build-desktop.yml` / `build-and-release.yml`

這兩個工作流原本負責構建 Tauri 桌面應用。v3.0 起按
[多會話 HTTP 模式重構設計 §7 決議](./architecture/multi-session-http-redesign.md#7-未提但需考虑的问题清单含决议)
**暫停維護**桌面模式：

- 工作流文件保留在倉庫，不主動刪除；
- CI 不再自動觸發桌面構建；
- 發佈不再附帶桌面二進制文件；
- 相關 `scripts/build_desktop.py` / `src-tauri/` 源碼保留，供未來可能恢復使用。

**如果你真的需要本地構建桌面版**（不推薦）：

```bash
# 需要 Rust 工具鏈
python scripts/build_desktop.py --release
```

但請注意 v3.0 的雙欄多會話 UI 尚未在 Tauri 殼下做過適配測試，行為可能異常。

## 🚀 v3.0 發佈建議流程

1. **確認 Pytest 全綠**：`uv run python -m pytest tests/`
2. **更新 CHANGELOG**：`CHANGELOG.zh-CN.md` / `CHANGELOG.zh-TW.md` / `CHANGELOG.en.md`
3. **本地驗證 daemon 啟動**：
   ```bash
   uv run python -m mcp_feedback_enhanced serve --http --port 18765
   # 另開終端
   curl http://127.0.0.1:18765/api/all-sessions
   ```
4. **手動觸發 "Auto Release to PyPI"**：選擇版本類型，確認發佈；
5. **發佈後驗證**：
   ```bash
   uvx mcp-feedback-enhanced@latest serve --http --port 18765
   ```

## 🔧 故障排除

**Q：發佈失敗，提示 PyPI 版本衝突**
A：檢查 PyPI 上是否已存在相同版本；`pyproject.toml` 版本號未 bump 就不能重發。

**Q：`PYPI_API_TOKEN` 權限問題**
A：GitHub Repo Settings → Secrets → Actions 檢查 `PYPI_API_TOKEN`；該 Token 需要 `upload` scope。

**Q：要恢復桌面構建**
A：恢復 `build-desktop.yml` 的觸發條件（目前應該是 disabled / 手動觸發）。相關實現細節曾在歷史文檔 `docs/DESKTOP_BUILD.md` 中，該文檔已隨 v3.0 Tauri 暫停維護而刪除，可從 git history 復原。

---

**相關文檔**：
- [多會話 HTTP 模式重構設計](./architecture/multi-session-http-redesign.md)（含桌面模式暫停決議）
- [阶段 2：HTTP Daemon 使用指南](./architecture/phase2-http-daemon-usage.md)
- [阶段 3：雙欄多會話 UI 使用指南](./architecture/phase3-multi-session-ui-usage.md)
