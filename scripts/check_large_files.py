"""Fail when a new tracked file exceeds the repository size limit."""

import subprocess
import sys
from pathlib import Path


MAX_BYTES = 25 * 1024 * 1024
# 仓库不使用 Git LFS：免费带宽配额按所有人的克隆下载计费，长期是负担。
# 新的大文件只能放入 GitHub Release 资产，由程序按需下载；存量模型豁免。
LEGACY_LARGE_FILES = {"assets/echo_model/echo.onnx"}


def git(*args: str) -> str:
    return subprocess.check_output(
        ("git", "-c", "core.quotepath=false", *args), text=True, encoding="utf-8"
    ).strip()


def main() -> int:
    failures = []
    legacy = []
    for relative_path in git("ls-files").splitlines():
        path = Path(relative_path)
        if not path.is_file() or path.stat().st_size <= MAX_BYTES:
            continue
        described = f"{relative_path}（{path.stat().st_size / 1024 / 1024:.1f} MiB）"
        if relative_path in LEGACY_LARGE_FILES:
            legacy.append(described)
        else:
            failures.append(described)
    if legacy:
        print("存量大文件（豁免，不要继续增加）：")
        print("\n".join(f"- {item}" for item in legacy))
    if failures:
        print(f"以下文件超过 {MAX_BYTES // 1024 // 1024} MiB，不要提交进 Git 仓库：", file=sys.stderr)
        print("请放入 GitHub Release 资产，由程序按需下载；不要提交到主仓库或更新仓库。", file=sys.stderr)
        print("\n".join(f"- {item}" for item in failures), file=sys.stderr)
        return 1
    print("大文件体积检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
