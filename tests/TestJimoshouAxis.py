import unittest

from src.char.JimoshouAxis import (
    FINISHER_MACRO,
    JIYAN_ULT_DURATION_MS,
    JimoshouAxisController,
    LOOP_MACRO,
    STARTUP_MACRO,
    is_jimoshou_team,
)
from src.combat.RawInputTimeline import RawInputAborted, compile_raw_timeline


class _FakeExecutor:
    def __init__(self):
        self.paused = False


class _FakeTask:
    def __init__(self):
        self._enabled = True
        self.paused = False
        self.executor = _FakeExecutor()
        self._exit = False

    def exit_is_set(self):
        return self._exit


class TestJimoshouAxis(unittest.TestCase):
    def test_team_requires_exact_slot_order(self):
        Jiyan = type("Jiyan", (), {})
        Mortefi = type("Mortefi", (), {})
        ShoreKeeper = type("ShoreKeeper", (), {})

        self.assertTrue(is_jimoshou_team([Jiyan(), Mortefi(), ShoreKeeper()]))
        self.assertFalse(is_jimoshou_team([ShoreKeeper(), Mortefi(), Jiyan()]))
        self.assertFalse(is_jimoshou_team([Jiyan(), ShoreKeeper(), Mortefi()]))

    def test_startup_macro_keeps_verified_raw_timeline(self):
        schedule = compile_raw_timeline(STARTUP_MACRO)

        self.assertEqual(60, len(schedule))
        self.assertEqual(("key", "2", "down", 78), (
            schedule[0].event.device,
            schedule[0].event.code,
            schedule[0].event.action,
            schedule[0].event.delay_after_ms,
        ))

        # 8.9 秒 probe 的最后一个实际输入必须保持在同一个绝对时间点，
        # 这样修正开局/循环边界不会改变已经实机验证通过的前半段。
        self.assertEqual(8909, schedule[35].at_ms)
        self.assertEqual("mouse", schedule[35].event.device)
        self.assertEqual("left", schedule[35].event.code)
        self.assertEqual("up", schedule[35].event.action)

        # 完整首次启动最终停在忌炎 R 抬起；最后的 11000ms 交给独立大招输出阶段。
        self.assertEqual(15452, schedule[-1].at_ms)
        self.assertEqual("key", schedule[-1].event.device)
        self.assertEqual("r", schedule[-1].event.code)
        self.assertEqual("up", schedule[-1].event.action)
        self.assertEqual(JIYAN_ULT_DURATION_MS, schedule[-1].event.delay_after_ms)

    def test_loop_macro_starts_after_initial_mortefi_shorekeeper_swap(self):
        # 循环收尾已经 EE -> 2 -> 3，因此下一轮从首次启动完成 2 -> 3 后的位置继续。
        self.assertEqual(STARTUP_MACRO[4:], LOOP_MACRO)
        schedule = compile_raw_timeline(LOOP_MACRO)
        self.assertEqual(56, len(schedule))
        self.assertEqual(("mouse", "left", "down"), (
            schedule[0].event.device,
            schedule[0].event.code,
            schedule[0].event.action,
        ))
        # 首次启动前四个事件占用 356ms；循环体内部其余相对时间保持不变。
        self.assertEqual(15096, schedule[-1].at_ms)
        self.assertEqual("r", schedule[-1].event.code)
        self.assertEqual("up", schedule[-1].event.action)

    def test_finisher_uses_double_e_then_mortefi_then_shorekeeper(self):
        down_codes = [
            event.code
            for event in FINISHER_MACRO
            if event.device == "key" and event.action == "down"
        ]
        self.assertEqual(["e", "e", "2", "3"], down_codes)


class TestAxisAbort(unittest.TestCase):
    """宏段绕过框架 sleep/next_frame，停止信号必须由控制器自己响应。"""

    def _controller(self):
        return JimoshouAxisController(_FakeTask())

    def test_no_stop_signal_means_no_abort(self):
        self.assertFalse(self._controller()._axis_should_abort())

    def test_task_disabled_aborts(self):
        controller = self._controller()
        controller.task._enabled = False
        self.assertTrue(controller._axis_should_abort())

    def test_exit_event_aborts(self):
        controller = self._controller()
        controller.task._exit = True
        self.assertTrue(controller._axis_should_abort())

    def test_pause_aborts(self):
        controller = self._controller()
        controller.task.paused = True
        self.assertTrue(controller._axis_should_abort())

        controller = self._controller()
        controller.task.executor.paused = True
        self.assertTrue(controller._axis_should_abort())

    def test_runner_is_wired_to_abort_check(self):
        controller = self._controller()
        self.assertEqual(controller.runner.should_abort, controller._axis_should_abort)

    def test_ult_phase_wait_aborts_on_stop(self):
        import time

        controller = self._controller()
        controller.task._enabled = False
        with self.assertRaises(RawInputAborted):
            controller._wait_until_ns(time.monotonic_ns() + 10_000_000_000)


if __name__ == "__main__":
    unittest.main()
