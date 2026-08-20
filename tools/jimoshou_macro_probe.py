"""忌炎 / 莫特斐 / 守岸人鼠标宏输入层验证。

默认只打印时间表，不发送任何游戏输入：
    py -3.12 tools/jimoshou_macro_probe.py

明确执行短验证段：
    py -3.12 tools/jimoshou_macro_probe.py --execute

验证目的只有一个：确认 PyDirectInput + 原始 down/up + 绝对 deadline 是否能比
PostMessage/角色 helper 更接近鼠标驱动宏。这个脚本不会启动自动战斗，也不会循环。
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import time
from pathlib import Path

# 允许直接从仓库根目录运行 tools 脚本。
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.combat.RawInputTimeline import RawInputEvent, RawInputTimelineRunner, compile_raw_timeline


# 视频 00:00 可见区域的连续原始事件。
# 编辑器每一行的数字表示“本事件执行后，到下一事件的等待时间”。
# 第一行只拍到了“2 抬起 78ms”，其前一行“2 按下”在画面上方；
# 这里暂按同类切人键常见的 78ms 推定其按住时间。除此之外均按录像可见数字转录。
JIMOSHO_VISIBLE_PROBE = (
    RawInputEvent("key", "2", "down", 78, "2 按下（录像缺失行，暂推定 78ms）"),
    RawInputEvent("key", "2", "up", 78, "2 抬起"),
    RawInputEvent("key", "3", "down", 100, "3 按下"),
    RawInputEvent("key", "3", "up", 100, "3 抬起"),
    RawInputEvent("mouse", "left", "down", 78, "左键按下 #1"),
    RawInputEvent("mouse", "left", "up", 450, "左键抬起 #1"),
    RawInputEvent("mouse", "left", "down", 78, "左键按下 #2"),
    RawInputEvent("mouse", "left", "up", 550, "左键抬起 #2"),
    RawInputEvent("key", "r", "down", 100, "R 按下"),
    # 录像这里是 R 抬起后等待 3000ms；probe 到 R 抬起即结束，因此不会真的多等 3 秒。
    RawInputEvent("key", "r", "up", 3000, "R 抬起"),
)

GAME_PROCESS = "client-win64-shipping.exe"


class PyDirectRawBackend:
    """直接调用 PyDirectInput 的 down/up；不使用 OKWW 的角色 helper。"""

    def __init__(self):
        import pydirectinput

        # PyDirectInput 默认的全局 pause 会直接污染宏 timing，必须关闭。
        pydirectinput.PAUSE = 0
        pydirectinput.FAILSAFE = False
        self.pydirectinput = pydirectinput

    def key_down(self, code: str) -> None:
        self.pydirectinput.keyDown(code)

    def key_up(self, code: str) -> None:
        self.pydirectinput.keyUp(code)

    def mouse_down(self, button: str) -> None:
        self.pydirectinput.mouseDown(button=button)

    def mouse_up(self, button: str) -> None:
        self.pydirectinput.mouseUp(button=button)


def _is_admin() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _foreground_process_name() -> str:
    import psutil
    import win32gui
    import win32process

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return ""
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        return psutil.Process(pid).name().casefold()
    except (psutil.Error, OSError):
        return ""


def _print_timeline() -> None:
    print("忌莫守 PyDirect 输入层 probe（不会调用任何角色 helper）")
    print("-" * 78)
    for index, scheduled in enumerate(compile_raw_timeline(JIMOSHO_VISIBLE_PROBE), start=1):
        event = scheduled.event
        print(
            f"{index:02d}  t={scheduled.at_ms:4d} ms  "
            f"{event.device:5s} {event.code:5s} {event.action:4s}  "
            f"after={event.delay_after_ms:4d} ms  {event.label}"
        )
    print("-" * 78)
    print("最后一个实际输入是 t=1612 ms 的 R 抬起；其后的 3000ms 只是原宏下一段等待。")


def _execute(countdown: int) -> int:
    if sys.platform != "win32":
        print("--execute 只支持 Windows。", file=sys.stderr)
        return 2
    if not _is_admin():
        print("请用管理员 PowerShell / VS Code 启动验证，避免游戏高完整性级别拒绝输入。", file=sys.stderr)
        return 2

    input(
        "\n即将执行约 1.6 秒的短输入验证。它不会自动循环。\n"
        "按 Enter 开始倒计时，然后立刻切回鸣潮；Ctrl+C 可在倒计时阶段取消。"
    )
    for remaining in range(max(1, countdown), 0, -1):
        print(f"{remaining}...", flush=True)
        time.sleep(1)

    foreground = _foreground_process_name()
    if foreground != GAME_PROCESS:
        print(
            f"已取消：当前前台进程是 {foreground or '<unknown>'}，不是 {GAME_PROCESS}。",
            file=sys.stderr,
        )
        return 3

    backend = PyDirectRawBackend()
    stats = RawInputTimelineRunner().run(JIMOSHO_VISIBLE_PROBE, backend)
    print(
        f"probe 完成：{stats.event_count} 个原始事件，"
        f"平均绝对调度偏差 {stats.average_abs_drift_ms:.3f} ms，"
        f"最大 {stats.max_abs_drift_ms:.3f} ms。"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="忌莫守 PyDirect 原始宏输入验证")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="真的向前台鸣潮发送短验证段；不加此参数只打印时间表",
    )
    parser.add_argument("--countdown", type=int, default=5, help="执行前切回游戏的倒计时秒数")
    args = parser.parse_args()

    _print_timeline()
    if not args.execute:
        print("dry-run：没有发送任何按键。需要实测时显式加 --execute。")
        return 0
    return _execute(args.countdown)


if __name__ == "__main__":
    raise SystemExit(main())
