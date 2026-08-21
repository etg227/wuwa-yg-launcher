"""忌莫守内置轴：忌炎(1) / 莫特斐(2) / 守岸人(3)。

这支轴不通过 BaseChar 的技能 helper 执行宏段。经过实机验证后，启动段直接使用
PyDirectInput 原始 key/mouse down/up + time.monotonic_ns 绝对 deadline，保留鼠标
宏中的按住时间和事件间隔，避免 PostMessage / click_resonance / switch_next_char
等额外等待污染极限衔接。

运行约束：
- 固定槽位：1 忌炎 / 2 莫特斐 / 3 守岸人；
- 首次开局默认 1 号位忌炎站场，第一步由宏切 2 号莫特斐，再切 3 号守岸人；
- 循环收尾为忌炎 EE -> 2 莫特斐 -> 3 守岸人，下一轮从守岸人动作段继续；
- 宏执行期间鸣潮必须保持前台；
- PyDirect 输入需要与游戏相同或更高的完整性级别，通常需要管理员权限。
"""

from __future__ import annotations

import ctypes
import sys
import time

from ok import Logger

from src.combat.RawInputTimeline import RawInputEvent, RawInputTimelineRunner

logger = Logger.get_logger(__name__)

AXIS_TEAM = ("Jiyan", "Mortefi", "ShoreKeeper")
GAME_PROCESS = "client-win64-shipping.exe"

# 忌炎 R 后的输出阶段。视频宏把 R 抬起后的 11000ms 作为输出窗口；
# 这里不空等，而是用原始左键持续攻击，绝对时间到点后进入收尾。
JIYAN_ULT_DURATION_MS = 11000
JIYAN_ULT_ATTACK_INTERVAL_MS = 110
JIYAN_ULT_ATTACK_HOLD_MS = 20

# 用户补充：忌炎大招结束后需要 EE -> 2 莫特斐 -> 3 守岸人。
# 视频末尾可见信息并不完整，因此第二次 E 与中间切 2 都按实战手法修正。
FINISHER_SECOND_E_GAP_MS = 80

BUILTIN_AXIS_ENTRY = {
    "name": "忌莫守轴",
    "team": "忌炎(1) / 莫特斐(2) / 守岸人(3)",
    "first": "忌炎（1号位）站场；固定槽位 1/2/3",
    "description": (
        "首次由忌炎站场，先切莫特斐再切守岸人进入启动宏；忌炎 R 后持续平 A，"
        "大招输出结束执行 EE→2→3，之后从守岸人的循环动作段继续。"
        "需要管理员权限且鸣潮保持前台。"
    ),
}


def _tap_events(device: str, code: str, hold_ms: int, wait_ms: int, label: str):
    return (
        RawInputEvent(device, code, "down", hold_ms, f"{label} 按下"),
        RawInputEvent(device, code, "up", wait_ms, f"{label} 抬起"),
    )


def _key(code: str, hold_ms: int, wait_ms: int, label: str | None = None):
    return _tap_events("key", code, hold_ms, wait_ms, label or code.upper())


def _mouse(hold_ms: int, wait_ms: int, label: str = "左键"):
    return _tap_events("mouse", "left", hold_ms, wait_ms, label)


# 首次启动从 1 号忌炎站场开始。视频开头第一颗 2 的按下行没有拍进画面，
# 但短 probe 已用 78ms 实机验证正确，因此保留该推定值。
#
# 注意最后 R 抬起的 wait=11000 只是原宏的输出窗口；RawInputTimelineRunner
# 不会在最后事件后额外等待，后续由 _run_jiyan_ult_phase() 接管。
STARTUP_MACRO = (
    *_key("2", 78, 78, "切莫特斐"),
    *_key("3", 100, 100, "切守岸人"),
    *_mouse(78, 450, "左键 #1"),
    *_mouse(78, 550, "左键 #2"),
    *_key("r", 100, 3000, "R #1"),

    *_mouse(47, 450, "R 后左键 #1"),
    *_mouse(62, 550, "R 后左键 #2"),
    *_mouse(78, 200, "R 后左键 #3"),
    *_mouse(500, 20, "长按左键"),
    *_key("q", 25, 10, "Q #1"),
    *_key("e", 25, 10, "E #1"),
    *_key("2", 100, 100, "切莫特斐 #2"),
    *_key("1", 100, 200, "切忌炎 #1"),
    *_key("e", 100, 420, "E #2"),
    *_key("3", 50, 50, "切守岸人 #2"),
    *_mouse(50, 450, "切3后左键 #1"),
    *_mouse(50, 550, "切3后左键 #2"),
    *_mouse(100, 50, "切3后左键 #3"),

    *_key("2", 78, 78, "切莫特斐 #3"),
    *_key("1", 78, 100, "切忌炎 #2"),
    *_key("q", 78, 600, "Q #2"),
    *_key("3", 109, 25, "切守岸人 #3"),
    *_mouse(500, 20, "长按左键 #2"),
    *_key("2", 100, 1350, "切莫特斐 #4"),
    *_key("e", 78, 20, "E #3"),
    *_key("r", 78, 1850, "R #2"),
    *_key("e", 150, 200, "E #4"),
    *_key("q", 145, 0, "Q #3"),
    *_key("1", 78, 700, "切忌炎 #3"),
    *_key("r", 78, JIYAN_ULT_DURATION_MS, "忌炎 R"),
)

# 循环收尾已经执行 EE -> 2 -> 3，因此下一轮已经处于“首次启动中完成 2 -> 3”
# 之后的同一状态。循环不能再重放开头的 2 -> 3，否则会重复切莫特斐并破坏协奏节奏。
LOOP_MACRO = STARTUP_MACRO[4:]

FINISHER_MACRO = (
    *_key("e", 78, FINISHER_SECOND_E_GAP_MS, "忌炎收尾 E #1"),
    *_key("e", 78, 20, "忌炎收尾 E #2"),
    # 2 -> 3 的相对间隔沿用已验证启动宏第一组切人的 78ms hold + 78ms wait。
    *_key("2", 78, 78, "切莫特斐重启"),
    *_key("3", 78, 0, "切守岸人重启"),
)


def _char_matches(char, expected_name: str) -> bool:
    return char is not None and any(cls.__name__ == expected_name for cls in type(char).mro())


def is_jimoshou_team(chars) -> bool:
    """只在槽位顺序完全为 1忌炎/2莫特斐/3守岸人时启用。"""

    if len(chars) < 3:
        return False
    return all(_char_matches(chars[index], name) for index, name in enumerate(AXIS_TEAM))


def _is_admin() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _foreground_game_hwnd() -> int:
    if sys.platform != "win32":
        return 0

    import psutil
    import win32gui
    import win32process

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return 0
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        process_name = psutil.Process(pid).name().casefold()
    except (psutil.Error, OSError):
        return 0
    return hwnd if process_name == GAME_PROCESS else 0


class _PyDirectRawBackend:
    """固定到本轮开始时的鸣潮前台 HWND，防止中途切窗后继续向其它程序发键。"""

    def __init__(self, expected_hwnd: int):
        import pydirectinput
        import win32gui

        pydirectinput.PAUSE = 0
        pydirectinput.FAILSAFE = False
        self.pydirectinput = pydirectinput
        self.win32gui = win32gui
        self.expected_hwnd = expected_hwnd

    def _guard(self):
        if self.win32gui.GetForegroundWindow() != self.expected_hwnd:
            raise RuntimeError("鸣潮已失去前台，已停止忌莫守原始输入轴")

    def key_down(self, code: str) -> None:
        self._guard()
        self.pydirectinput.keyDown(code)

    def key_up(self, code: str) -> None:
        # 抬起事件即使已经切窗也要发出去，避免留下“按住”状态。
        self.pydirectinput.keyUp(code)

    def mouse_down(self, button: str) -> None:
        self._guard()
        self.pydirectinput.mouseDown(button=button)

    def mouse_up(self, button: str) -> None:
        # 与 key_up 相同：释放优先于前台保护。
        self.pydirectinput.mouseUp(button=button)


class JimoshouAxisController:
    """由 AutoCombatTask 直接调用的队伍级控制器；宏段期间不进入角色 do_perform。"""

    SLOT_JIYAN = 0
    SLOT_MORTEFI = 1
    SLOT_SHOREKEEPER = 2
    SLOT_SYNC_TIMEOUT = 1.5

    def __init__(self, task):
        self.task = task
        self.runner = RawInputTimelineRunner()
        self.first_cycle = True

    def run_cycle(self) -> bool:
        if not is_jimoshou_team(self.task.chars):
            return False
        if not _is_admin():
            logger.error("忌莫守轴需要管理员权限；本轮不发送 PyDirect 输入")
            return False

        hwnd = _foreground_game_hwnd()
        if not hwnd:
            logger.error("忌莫守轴要求鸣潮保持前台；未检测到游戏前台，本轮停止")
            return False

        backend = _PyDirectRawBackend(hwnd)

        try:
            if self.first_cycle:
                # 首次开局必须保留默认的 1 号忌炎站场。不能像旧实现一样先强制切 3，
                # 否则 STARTUP_MACRO 的第一颗 2 就失去“忌炎 -> 莫特斐”的语义。
                if not self._slot_is(self.SLOT_JIYAN):
                    logger.error("忌莫守首次开局要求 1 号位忌炎站场；未主动补切，停止本轮")
                    return False
                cycle_macro = STARTUP_MACRO
                cycle_name = "startup"
            else:
                # 上一轮 FINISHER 已经完成 EE -> 2 -> 3；此时正好对应首次启动
                # 2 -> 3 之后的状态，所以循环从守岸人的动作段继续，跳过最前四个原始事件。
                if not self._slot_is(self.SLOT_SHOREKEEPER):
                    logger.error("忌莫守循环起点应为 3 号位守岸人；状态不同步，停止本轮")
                    return False
                cycle_macro = LOOP_MACRO
                cycle_name = "loop"

            logger.info(f"Jimoshou cycle start: raw {cycle_name} macro")
            startup_stats = self.runner.run(cycle_macro, backend)
            logger.info(
                f"Jimoshou {cycle_name} macro complete: events={startup_stats.event_count} "
                f"avg_drift={startup_stats.average_abs_drift_ms:.3f}ms "
                f"max_drift={startup_stats.max_abs_drift_ms:.3f}ms"
            )

            self._run_jiyan_ult_phase(backend)

            finisher_stats = self.runner.run(FINISHER_MACRO, backend)
            logger.info(
                f"Jimoshou finisher complete: events={finisher_stats.event_count} "
                f"avg_drift={finisher_stats.average_abs_drift_ms:.3f}ms "
                f"max_drift={finisher_stats.max_abs_drift_ms:.3f}ms"
            )

            if not self._wait_slot(self.SLOT_SHOREKEEPER, self.SLOT_SYNC_TIMEOUT):
                logger.warning("忌莫守收尾 EE→2→3 后未确认守岸人；补按一次 3 后重新同步")
                self._raw_key_tap(backend, "3", 78)
                if not self._wait_slot(self.SLOT_SHOREKEEPER, self.SLOT_SYNC_TIMEOUT):
                    logger.error("忌莫守轴无法确认守岸人重新站场，停止循环")
                    return False

            self.first_cycle = False
            logger.info("Jimoshou cycle complete: ShoreKeeper ready for loop body")
            return True
        except RuntimeError as error:
            logger.warning(f"忌莫守轴已中止：{error}")
            return False

    def _slot_is(self, expected_index: int) -> bool:
        in_team, current_index, _ = self.task.in_team()
        if in_team and current_index == expected_index:
            self._sync_current_flags(current_index)
            return True
        return False

    def _wait_slot(self, expected_index: int, timeout: float) -> bool:
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            self.task.next_frame()
            in_team, current_index, _ = self.task.in_team()
            if in_team and current_index == expected_index:
                self._sync_current_flags(current_index)
                return True
            time.sleep(0.02)
        return False

    def _sync_current_flags(self, current_index: int) -> None:
        for char in self.task.chars:
            if char is not None:
                char.is_current_char = (char.index == current_index)

    @staticmethod
    def _raw_key_tap(backend, code: str, hold_ms: int) -> None:
        backend.key_down(code)
        time.sleep(hold_ms / 1000)
        backend.key_up(code)

    @staticmethod
    def _wait_until_ns(target_ns: int) -> None:
        spin_window_ns = 1_000_000
        while True:
            remaining_ns = target_ns - time.monotonic_ns()
            if remaining_ns <= 0:
                return
            if remaining_ns > spin_window_ns:
                time.sleep((remaining_ns - spin_window_ns) / 1_000_000_000)
                continue

    def _run_jiyan_ult_phase(self, backend) -> None:
        """忌炎 R 后持续原始左键，11 秒 deadline 到点后进入 EE→2→3。"""

        start_ns = time.monotonic_ns()
        end_ns = start_ns + JIYAN_ULT_DURATION_MS * 1_000_000
        interval_ns = JIYAN_ULT_ATTACK_INTERVAL_MS * 1_000_000
        hold_ns = JIYAN_ULT_ATTACK_HOLD_MS * 1_000_000

        click_index = 0
        logger.info(
            f"Jimoshou Jiyan ult phase: duration={JIYAN_ULT_DURATION_MS}ms "
            f"interval={JIYAN_ULT_ATTACK_INTERVAL_MS}ms"
        )

        while True:
            down_ns = start_ns + click_index * interval_ns
            up_ns = down_ns + hold_ns
            if up_ns >= end_ns:
                break

            self._wait_until_ns(down_ns)
            backend.mouse_down("left")
            try:
                self._wait_until_ns(up_ns)
            finally:
                backend.mouse_up("left")
            click_index += 1

        self._wait_until_ns(end_ns)
        logger.info(f"Jimoshou Jiyan ult phase complete: raw clicks={click_index}")
