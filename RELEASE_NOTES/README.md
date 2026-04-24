# 发布说明管理 / Release Notes

本目录存放本 fork（**MCP Interactive Feedback HTTP fork**）的结构化发布说明。
自用仓库，**不**发布到 PyPI；GitHub Actions 只负责「打版本号 → 打 tag →
基于本目录的 CHANGELOG 生成 GitHub Release」。桌面构建已移除。

## 📁 目录结构

```
RELEASE_NOTES/
├── README.md                 # 本文件
├── template.md               # 单版本发布说明模板（手写 CHANGELOG 条目时参考）
├── CHANGELOG.en.md           # 英文完整更新历史
├── CHANGELOG.zh-CN.md        # 简体中文完整更新历史
├── CHANGELOG.zh-TW.md        # 繁体中文完整更新历史
└── SIMPLIFIED_WORKFLOW.md    # 发布流程说明（workflow 怎么用、条目怎么写）
```

> 上游 v2.x 的历史条目已从这三个 CHANGELOG 移除；本 fork 的历史从
> **v3.0.0** 起算。

## 🤖 与 GitHub Actions 的联动

手动触发 `.github/workflows/publish.yml`（Auto Release）时，workflow 会：

1. 按 `version_type` / `custom_version` 升级 `pyproject.toml`、`.bumpversion.cfg`、
   `src/mcp_feedback_enhanced/__init__.py` 中的版本字符串；
2. 从 `CHANGELOG.en.md` 里抽取对应 `[vX.Y.Z]` 块的 Highlights / New Features，
   再拼接多语言 CHANGELOG 链接，生成 GitHub Release body；
3. commit + 打 tag + push；
4. 创建 GitHub Release（只是 tag + release notes，**不**附带任何 asset）。

所以 **发版前一定要先手动把三份 CHANGELOG 更新到位**，workflow 不会替你写。

## 📝 新版本撰写流程

1. 在 `CHANGELOG.en.md`、`CHANGELOG.zh-CN.md`、`CHANGELOG.zh-TW.md` **顶部**
   添加新版本条目（紧跟首段说明之后）。
2. 条目标题必须遵守格式：`## [vX.Y.Z] - YYYY-MM-DD - 简短标题`，workflow
   会按这个格式匹配。
3. 至少写一个 `### 🌟 Highlights`（或 `### 🌟 版本亮点` / `### 🌟 版本亮點`）
   段，workflow 会从这里抽取前 5 行作为 Release Highlights。
4. 参考 `template.md` 的章节结构保持三语一致。
5. 其余节（✨ 新功能、🐛 问题修复、🚀 改进等）按实际内容填。

## 🎨 格式约定

- **表情符号对齐**：同一类变更在三语之间用一样的前缀 emoji。
- **条目简洁**：每条一行说清楚「做了什么 / 影响是什么」。
- **最新版本置顶**：新条目加在文件上方，旧条目往下滚。
- **Issue / PR 引用**：如有相关 issue，用 `(fixes #NN)` 的格式标注。

## 🔧 常见问答

**Q：发 release 时 workflow 报 "vX.Y.Z not found in CHANGELOG.xxx.md"**
A：忘了先更新 CHANGELOG。workflow 不会中断，但生成出来的 Release Notes 只
有兜底内容，版本标题也会变成 "Latest Release"。建议先补 CHANGELOG 再触发。

**Q：这个 fork 怎么安装？**
A：不走 PyPI。详见仓库根目录 `README.md`「Installation」部分：`git clone`
后 `uv sync`，然后 `uv run mcp-interactive-feedback serve --http`。
