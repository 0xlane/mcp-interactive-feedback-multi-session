# GitHub Actions 工作流程说明 / Workflows (v3.0+)

本仓库是 **MCP Interactive Feedback** 的自用 fork：
**不**发布到 PyPI，也**不再**构建 Tauri 桌面应用。
仓库里现在只剩一个 workflow：`publish.yml`（Auto Release）。

This repository is a self-use fork of **MCP Interactive Feedback**. It is
**not** published to PyPI and no longer builds the Tauri desktop shell.
Only one workflow remains in the repo: `publish.yml` (Auto Release).

## 🏗️ 现行工作流程 / Active Workflow

### `.github/workflows/publish.yml` — Auto Release

**用途 / Purpose**：版本升级 + GitHub Release（纯 tag + release notes，不附带
任何 asset）。

**触发 / Trigger**：手动触发（`workflow_dispatch`）。

**输入 / Inputs**：

| 参数 / Input | 说明 / Description |
|---|---|
| `version_type` | `patch` / `minor` / `major`，默认 `patch`。若 `custom_version` 填写则此项忽略 |
| `custom_version` | 自定义版本号（如 `3.1.0`），**会覆盖** `version_type` |

**流程 / Steps**：

1. `checkout` + 安装 `uv` / Python / 依赖；
2. 按 `custom_version` 或 `bump2version {patch|minor|major}` 更新
   `pyproject.toml` / `.bumpversion.cfg` / `src/mcp_feedback_enhanced/__init__.py`；
3. `Verify CHANGELOG files` —— 检查 3 份 `RELEASE_NOTES/CHANGELOG.*.md` 是否
   含 `[vX.Y.Z]` 条目（缺失只警告，不中断）；
4. `Extract release highlights` —— 从 `CHANGELOG.en.md` 抽 `### 🌟 Highlights`
   前 5 行，兜底取 `### ✨ New Features` 的前 4 条；
5. `Generate release body` —— 拼接 Highlights + 三语 CHANGELOG 链接 + 仓库信息，
   生成 `release_body.md`；
6. `git commit` + `git tag vX.Y.Z` + `git push`；
7. `softprops/action-gh-release@v2` 创建 GitHub Release（`body_path: release_body.md`）；
8. 输出 summary。

**使用方式 / Usage**：

1. 先手动更新三份 `RELEASE_NOTES/CHANGELOG.*.md`（见 [SIMPLIFIED_WORKFLOW](../RELEASE_NOTES/SIMPLIFIED_WORKFLOW.md)）；
2. GitHub → **Actions** → **Auto Release** → **Run workflow**；
3. 选择 `version_type` 或填 `custom_version`，确认即可。

## 🚫 已移除的工作流程 / Removed Workflows

| 文件 / File | 状态 / Status | 原因 / Reason |
|---|---|---|
| `build-desktop.yml` | **已删除** | Tauri 桌面应用于 v3.0 停止维护 |
| `build-and-release.yml` | **已删除** | 只是 `build-desktop.yml + publish.yml` 的 wrapper，桌面没了它也没意义 |

**如果以后想恢复桌面构建**：从 git 历史里找回 `build-desktop.yml` 和
`scripts/build_desktop.py`，再把 `publish.yml` 里对应桌面产物的校验/上传
步骤加回来。v3.0 的双栏多会话 UI 没在 Tauri 壳里做过适配测试，要先核对。

## ❌ 不做的事情 / What the Workflow Does NOT Do

- ❌ **不构建 wheel / sdist**：`uv build` 步骤已移除；
- ❌ **不发布到 PyPI**：`twine check` / `pypa/gh-action-pypi-publish` 步骤已移除；
- ❌ **不构建桌面二进制**：`build-desktop.yml` 已删除；
- ❌ **Release 不附带任何 asset**：只是 tag + release notes。

## 🚀 标准发布流程 / Standard Release Flow

1. 本地开发、测试通过（`uv run python -m pytest tests/`）；
2. 更新三份 CHANGELOG：`CHANGELOG.en.md` / `CHANGELOG.zh-CN.md` / `CHANGELOG.zh-TW.md`；
3. 推到 `main`；
4. 手动触发 **Auto Release** workflow，选版本类型；
5. 去 **Releases** 页确认 tag 和 release body 生成正确。

## 🔧 故障排除 / Troubleshooting

**Q：workflow 抱怨 `vX.Y.Z not found in CHANGELOG.xxx.md`**
A：忘了先把新版本条目补到三份 CHANGELOG。这只是 warning 不会中断，但生成
出来的 Release Notes 只有兜底文案（"Latest Release" + 默认 highlights），
通常建议补完 CHANGELOG 再重跑。

**Q：要重新打一个已经存在的版本号 tag**
A：先本地 `git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z` 把远端
tag 清掉，再把 `pyproject.toml` 等文件里的版本号手动回到上一版；然后通过
`custom_version` 重新触发 workflow。

**Q：Release 需要附带 wheel 给别人用怎么办**
A：当前 workflow 不产 wheel。如果真要给人 wheel：
1. 本地 `uv build` 打出 `dist/*.whl` + `dist/*.tar.gz`；
2. 在 GitHub Release 页面手动上传到对应 tag 的 Release assets。
把这个能力重新自动化需要在 `publish.yml` 里加回 `uv build` 步骤 + 配置
`softprops/action-gh-release` 的 `files` 参数。

---

**相关文档 / Related**

- [`RELEASE_NOTES/SIMPLIFIED_WORKFLOW.md`](../RELEASE_NOTES/SIMPLIFIED_WORKFLOW.md)
  —— 发布流程使用者视角的 step-by-step 指南
- [`RELEASE_NOTES/README.md`](../RELEASE_NOTES/README.md)
  —— RELEASE_NOTES 目录结构与 workflow 联动说明
- [`architecture/multi-session-http-redesign.md`](./architecture/multi-session-http-redesign.md)
  —— 桌面暂停决议的背景
