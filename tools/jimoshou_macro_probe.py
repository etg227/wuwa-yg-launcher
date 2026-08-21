"""忌炎 / 莫特斐 / 守岸人鼠标宏输入层验证。

默认只打印时间表，不发送任何游戏输入：
    py -3.12 tools/jimoshou_macro_probe.py

明确执行短验证段：
    py -3.12 tools/jimoshou_macro_probe.py --execute

执行延长验证段：
    py -3.12 tools/jimoshou_macro_probe.py --execute --extended

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


# 视频开头可见区域的连续原始事件。
# 编辑器每一行的数字表示“本事件执行后，到下一事件的等待时间”。
# 第一行只拍到了“2 抬起 78ms”，其前一行“2 按下”在画面上方；
# 这里暂按同类切人键常见的 78ms 推定其按住时间。除此之外均按录像可见数字转录。
JIMOSHO_SHORT_PROBE = (
    RawInputEvent("key", "2", "down", 78, "2 按下（录像缺失行，暂推定 78ms）"),
    RawInputEvent("key", "2", "up", 78, "2 抬起"),
    RawInputEvent("key", "3", "down", 100, "3 按下"),
    RawInputEvent("key", "3", "up", 100, "3 抬起"),
    RawInputEvent("mouse", "left", "down", 78, "左键按下 #1"),
    RawInputEvent("mouse", "left", "up", 450, "左键抬起 #1"),
    RawInputEvent("mouse", "left", "down", 78, "左键按下 #2"),
    RawInputEvent("mouse", "left", "up", 550, "左键抬起 #2"),
    RawInputEvent("key", "r", "down", 100, "R 按下"),
    RawInputEvent("key", "r", "up", 3000, "R 抬起"),
)

# 延长段继续按视频 f_10 / f_20 / f_25 / f_30 / f_35 可见行逐项转录。
# 重点覆盖旧方案最容易开始漂移的区间：长等待、连续普攻、长按普攻、Q/E 和连续切人。
JIMOSHO_EXTENDED_TAIL = (
    RawInputEvent("mouse", "left", "down", 47, "R 后左键按下 #3"),
    RawInputEvent("mouse", "left", "up", 450, "R 后左键抬起 #3"),
    RawInputEvent("mouse", "left", "down", 62, "R 后左键按下 #4"),
    RawInputEvent("mouse", "left", "up", 550, "R 后左键抬起 #4"),
    RawInputEvent("mouse", "left", "down", 78, "R 后左键按下 #5"),
    RawInputEvent("mouse", "left", "up", 200, "R 后左键抬起 #5"),
    RawInputEvent("mouse", "left", "down", 500, "长按左键按下"),
    RawInputEvent("mouse", "left", "up", 20, "长按左键抬起"),
    RawInputEvent("key", "q", "down", 25, "Q 按下"),
    RawInputEvent("key", "q", "up", 10, "Q 抬起"),
    RawInputEvent("key", "e", "down", 25, "E 按下 #1"),
    RawInputEvent("key", "e", "up", 10, "E 抬起 #1"),
    RawInputEvent("key", "2", "down", 100, "2 按下 #2"),
    RawInputEvent("key", "2", "up", 100, "2 抬起 #2"),
    RawInputEvent("key", "1", "down", 100, "1 按下 #1"),
    RawInputEvent("key", "1", "up", 200, "1 抬起 #1"),
    RawInputEvent("key", "e", "down", 100, "E 按下 #2"),
    RawInputEvent("key", "e", "up", 420, "E 抬起 #2"),
    RawInputEvent("key", "3", "down", 50, "3 按下 #2"),
    RawInputEvent("key", "3", "up", 50, "3 抬起 #2"),
    RawInputEvent("mouse", "left", "down", 50, "切 3 后左键按下 #1"),
    RawInputEvent("mouse", "left", "up", 450, "切 3 后左键抬起 #1"),
    RawInputEvent("mouse", "left", "down", 50, "切 3 后左键按下 #2"),
    RawInputEvent("mouse", "left", "up", 550, "切 3 后左键抬起 #2"),
    RawInputEvent("mouse", "left", "down", 100, "切 3 后左键按下 #3"),
    RawInputEvent("mouse", "left", "up", 50, "切 3 后左键抬起 #3"),
)

JIMOSHO_EXTENDED_PROBE = JIMOSHO_SHORT_PROBE + JIMOSHO_EXTENDED_TAIL
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


def _wait_for_game_foreground(timeout_s: float = 20.0, stable_s: float = 0.25) -> bool:
    """等待鸣潮真正成为前台，并连续保持一小段时间后再开始 probe。"""

    print(
        f"倒计时结束。现在切回鸣潮；检测到 {GAME_PROCESS} 连续前台 "
        f"{stable_s:.2f}s 后自动执行（最多等待 {timeout_s:.0f}s）。",
        flush=True,
    )
    deadline = time.monotonic() + timeout_s
    stable_since = None
    last_reported = None

    while time.monotonic() < deadline:
        foreground = _foreground_process_name()
        if foreground == GAME_PROCESS:
            if stable_since is None:
                stable_since = time.monotonic()
                print("已检测到鸣潮前台，确认窗口稳定...", flush=True)
            elif time.monotonic() - stable_since >= stable_s:
                return True
        else:
            stable_since = None
            if foreground != last_reported:
                print(f"等待鸣潮前台；当前：{foreground or '<unknown>'}", flush=True)
                last_reported = foreground
        time.sleep(0.05)

    return False


def _timeline_last_ms(events) -> int:
    schedule = compile_raw_timeline(events)
    return schedule[-1].at_ms if schedule else 0


def _print_timeline(events, name: str) -> None:
    print(f"忌莫守 PyDirect 输入层 probe：{name}（不会调用任何角色 helper）")
    print("-" * 78)
    for index, scheduled in enumerate(compile_raw_timeline(events), start=1):
        event = scheduled.event
        print(
            f"{index:02d}  t={scheduled.at_ms:4d} ms  "
            f"{event.device:5s} {event.code:5s} {event.action:4s}  "
            f"after={event.delay_after_ms:4d} ms  {event.label}"
        )
    print("-" * 78)
    print(f"最后一个实际输入位于 t={_timeline_last_ms(events)} ms；最后一行 after-delay 不会额外等待。")


def _execute(events, countdown: int, name: str) -> int:
    if sys.platform != "win32":
        print("--execute 只支持 Windows。", file=sys.stderr)
        return 2
    if not _is_admin():
        print("请用管理员 PowerShell / VS Code 启动验证，避免游戏高完整性级别拒绝输入。", file=sys.stderr)
        return 2

    duration_s = _timeline_last_ms(events) / 1000
    input(
        f"\n即将执行约 {duration_s:.1f} 秒的{name}输入验证。它不会自动循环。\n"
        "按 Enter 开始倒计时；倒计时结束后脚本会等待鸣潮真正成为前台再执行。"
    )
    for remaining in range(max(1, countdown), 0, -1):
        print(f"{remaining}...", flush=True)
        time.sleep(1)

    if not _wait_for_game_foreground():
        foreground = _foreground_process_name()
        print(
            f"已取消：20 秒内没有检测到稳定的鸣潮前台；当前前台是 {foreground or '<unknown>'}。",
            file=sys.stderr,
        )
        return 3

    backend = PyDirectRawBackend()
    stats = RawInputTimelineRunner().run(events, backend)
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
        help="真的向前台鸣潮发送验证段；不加此参数只打印时间表",
    )
    parser.add_argument(
        "--extended",
        action="store_true",
        help="使用约 9 秒延长段；默认仍使用已验证通过的约 1.6 秒短段",
    )
    parser.add_argument("--countdown", type=int, default=5, help="开始等待鸣潮前台前的倒计时秒数")
    args = parser.parse_args()

    events = JIMOSHO_EXTENDED_PROBE if args.extended else JIMOSHO_SHORT_PROBE
    name = "延长段" if args.extended else "短段"
    _print_timeline(events, name)
    if not args.execute:
        print("dry-run：没有发送任何按键。需要实测时显式加 --execute。")
        return 0
    return _execute(events, args.countdown, name)


if __name__ == "__main__":
    raise SystemExit(main())
