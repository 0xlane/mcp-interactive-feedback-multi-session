# 发布流程说明 / Release Workflow

## 🎯 概述 / Overview

此仓库是 **MCP Interactive Feedback** 的自用 fork，**不**发布到 PyPI，
也不再构建 Tauri 桌面应用。`.github/workflows/publish.yml` 只负责：

- 自动版本升级 / 手动指定版本号；
- 基于 `RELEASE_NOTES/CHANGELOG.*.md` 生成 GitHub Release body；
- 打 tag、推送、创建 GitHub Release（纯 tag + release notes，不附带 wheel/sdist）。

This repository is a self-use fork of **MCP Interactive Feedback**. It is
**not** published to PyPI and no longer builds the Tauri desktop shell. The
`publish.yml` workflow only bumps the version, generates release notes from
the CHANGELOG files, tags the commit, and creates a GitHub Release (tag +
notes only, no wheels).

## 📋 发布流程 / Release Process

### 1. 更新 CHANGELOG 文件 / Update CHANGELOG Files

在触发 workflow **之前**，请手动更新以下三份文件，把新版本条目加在顶部：
Before triggering the workflow, manually update the three files below and
add the new version entry at the top:

- `RELEASE_NOTES/CHANGELOG.en.md`
- `RELEASE_NOTES/CHANGELOG.zh-TW.md`
- `RELEASE_NOTES/CHANGELOG.zh-CN.md`

### 2. 条目格式 / Entry Format

每个版本按以下格式写；标题行的 `[vX.Y.Z]` 必须与实际版本号对上（workflow
会用 `sed` 按这个 marker 抽取段落）：

Each version entry must use the format below. The `[vX.Y.Z]` marker in the
heading must match the actual version (the workflow uses it with `sed` to
extract the section):

```markdown
## [vX.Y.Z] - YYYY-MM-DD - 简短标题 / Short Title

### 🌟 Highlights / 亮点 / 亮點
本次发布的重点摘要，3-5 行最佳。

### ✨ New Features / 新功能
- 🆕 **功能名称**：一句话说明

### 🐛 Bug Fixes / 错误修复
- 🔧 **问题修复**：一句话说明

### 🚀 Improvements / 改进
- ⚡ **性能 / UX**：一句话说明

---
```

> workflow 从 `CHANGELOG.en.md` 抽取 `### 🌟 Highlights` 下面的前 5 行（或
> 没有 Highlights 时退而取 `### ✨ New Features` 下的前 4 行）作为 Release
> 的 Key Highlights。

### 3. 触发发布 / Trigger the Release

1. GitHub → **Actions** → **Auto Release**；
2. **Run workflow**；
3. 选择 `version_type`（patch / minor / major）或在 `custom_version` 填
   具体版本号（`custom_version` 优先于 `version_type`）；
4. 确认；workflow 会完成 bump → commit → tag → push → Create GitHub Release。

### 📊 版本类型 / Version Type

| 类型 / Type | 场景 / When to use | 范例 / Example |
|---|---|---|
| **patch** | 🐛 Bug 修复、📝 文档、🔒 安全补丁、🎨 UI 微调 | `3.0.0 → 3.0.1` |
| **minor** | 🆕 新功能、🚀 向后兼容的增强、🌐 新语言支持 | `3.0.0 → 3.1.0` |
| **major** | 💥 破坏性变更、🏗️ 架构重构、🔄 协议/API 变更 | `3.0.0 → 4.0.0` |

自问自答的选型流程：

1. **会不会破坏已有行为？** → 是：Major；否：下一问。
2. **是否新增了功能？** → 是：Minor；否：下一问。
3. **只是修修补补？** → Patch。

## 🔄 Workflow 内部做什么 / What the Workflow Does

1. ✅ 版本号升级（改 `pyproject.toml` / `.bumpversion.cfg` / `__init__.py`）
2. ✅ 校验三份 CHANGELOG 是否包含新版本号（缺失只会告警，不中断）
3. ✅ 从 `CHANGELOG.en.md` 抽取 Highlights → 生成 Release body
4. ✅ `git commit` + `git tag vX.Y.Z` + `git push`
5. ✅ `softprops/action-gh-release@v2` 创建 GitHub Release

**不**做的事情：

- ❌ 构建 wheel（`uv build` 步骤已移除）
- ❌ 发布到 PyPI（`twine` / `pypa/gh-action-pypi-publish` 已移除）
- ❌ 构建 Tauri 桌面应用（`build-desktop.yml` 已删除）
- ❌ 附带任何 Release Asset（纯 tag + release notes）

## ⚠️ 注意事项 / Important Notes

1. **CHANGELOG 必须手动维护**，workflow 不会替你生成条目。
   CHANGELOG entries are **manually** written — the workflow does not generate them.

2. **格式要严格**：标题 `## [vX.Y.Z] - ... - ...`、亮点段 `### 🌟 Highlights`
   这两个 marker 直接影响 workflow 的正则抽取，别随意改。

3. **安装说明**：因为不走 PyPI，别在 Release body / CHANGELOG 里写
   `uvx mcp-interactive-feedback@latest`，workflow 生成的 body 已经用
   `git clone + uv sync + uv run` 替代了。

## 🚀 优点 / Benefits

- ✅ 发布链路够短：改 CHANGELOG → 点 workflow → GitHub Release；
- ✅ 单一真实来源：版本号 + 发布说明全部归档在仓库里；
- ✅ 没有 PyPI / 没有桌面构建，没有 secrets，发版零摩擦。
