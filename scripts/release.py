#!/usr/bin/env python3
"""
本地發布腳本
用法：
  python scripts/release.py patch   # 3.0.0 -> 3.0.1
  python scripts/release.py minor   # 3.0.0 -> 3.1.0
  python scripts/release.py major   # 3.0.0 -> 4.0.0
"""

import re
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd, check=True):
    """執行命令並返回結果"""
    print(f"🔨 執行: {cmd}")
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        print(f"❌ 錯誤: {result.stderr}")
        sys.exit(1)
    return result


def get_current_version():
    """從 pyproject.toml 獲取當前版本"""
    pyproject_path = Path("pyproject.toml")
    content = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'version = "([^"]+)"', content)
    if match:
        return match.group(1)
    raise ValueError("無法找到版本號")


def bump_version(version_type):
    """更新版本號"""
    if version_type not in ["patch", "minor", "major"]:
        print("❌ 版本類型必須是: patch, minor, major")
        sys.exit(1)

    current = get_current_version()
    print(f"📦 當前版本: {current}")

    # 使用 bump2version with allow-dirty
    run_cmd(f"uv run bump2version --allow-dirty {version_type}")

    new_version = get_current_version()
    print(f"🎉 新版本: {new_version}")

    return current, new_version


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    version_type = sys.argv[1]

    print("🚀 開始發布流程...")

    # 檢查 Git 狀態（僅提示，不阻止）
    result = run_cmd("git status --porcelain", check=False)
    if result.stdout.strip():
        print("⚠️  有未提交的變更：")
        print(result.stdout)
        print("💡 將繼續執行（使用 --allow-dirty 模式）")

    # 更新版本
    old_version, new_version = bump_version(version_type)

    # 建置套件
    print("📦 建置套件...")
    run_cmd("uv build")

    # 檢查套件
    print("🔍 檢查套件...")
    run_cmd("uv run twine check dist/*")

    # 提交所有變更（包括版本更新）
    print("💾 提交版本更新...")
    run_cmd("git add .")
    run_cmd(f'git commit -m "🔖 Release v{new_version}"')
    run_cmd(f'git tag "v{new_version}"')

    # 詢問是否發布
    print(f"\n✅ 準備發布版本 {old_version} -> {new_version}")
    choice = input("是否發布到 PyPI？ (y/N): ")

    if choice.lower() == "y":
        print("🚀 發布到 PyPI...")
        run_cmd("uv run twine upload dist/*")

        print("📤 推送到 GitHub...")
        run_cmd("git push origin main")
        run_cmd(f'git push origin "v{new_version}"')

        print(f"🎉 發布完成！版本 v{new_version} 已上線")
        print("📦 安裝命令: uvx mcp-interactive-feedback")
    else:
        print("⏸️  發布已取消，版本已更新但未發布")
        print("💡 您可以稍後手動發布: uv run twine upload dist/*")


if __name__ == "__main__":
    main()
