import unittest

from src.char.JimoshouAxis import (
    COMBAT_PROBE_MIN_IDLE_MS,
    COMBAT_PROBE_MISS_LIMIT,
    FINISHER_MACRO,
    JIYAN_ULT_DURATION_MS,
    JimoshouAxisController,
    LOOP_MACRO,
    STARTUP_MACRO,
    is_jimoshou_team,
)
from src.combat.RawInputTimeline import RawInputAborted, RawInputEvent, compile_raw_timeline


class _FakeExecutor:
    def __init__(self):
        self.paused = False


class _FakeScene:
    def __init__(self):
        self.value = None

    def in_combat(self):
        return self.value


class _FakeTask:
    def __init__(self):
        self._enabled = True
        self.paused = False
        self.executor = _FakeExecutor()
        self._exit = False
        self._in_combat = True
        self.scene = _FakeScene()
        self.combat_end_condition = None
        self.health_bar_visible = True
        self.next_frame_calls = 0
        self.current_index = 0
        self.chars = []

    def exit_is_set(self):
        return self._exit

    def next_frame(self):
        self.next_frame_calls += 1

    def check_health_bar(self):
        return self.health_bar_visible

    def in_team(self):
        return True, self.current_index, None


class _RecordingBackend:
    def __init__(self):
        self.calls = []

    def key_down(self, code):
        self.calls.append(("key_down", code))

    def key_up(self, code):
        self.calls.append(("key_up", code))


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

    def test_known_out_of_combat_state_aborts(self):
        controller = self._controller()
        controller.task._in_combat = False
        self.assertTrue(controller._axis_should_abort())

    def test_runner_is_wired_to_abort_and_event_probe(self):
        controller = self._controller()
        self.assertEqual(controller.runner.should_abort, controller._axis_should_abort)
        self.assertEqual(controller.runner.after_event, controller._after_raw_event)

    def test_ult_phase_wait_aborts_on_stop(self):
        import time

        controller = self._controller()
        controller.task._enabled = False
        with self.assertRaises(RawInputAborted):
            controller._wait_until_ns(time.monotonic_ns() + 10_000_000_000)

    def test_wait_slot_raises_instead_of_returning_failed_sync_on_stop(self):
        controller = self._controller()
        controller.task._enabled = False
        with self.assertRaises(RawInputAborted):
            controller._wait_slot(controller.SLOT_SHOREKEEPER, 1.0)
        self.assertEqual(controller.task.next_frame_calls, 0)

    def test_raw_key_tap_releases_key_when_abort_happens_during_hold(self):
        controller = self._controller()
        backend = _RecordingBackend()

        def abort_wait(_target_ns):
            raise RawInputAborted("stop during hold")

        controller._wait_until_ns = abort_wait
        with self.assertRaises(RawInputAborted):
            controller._raw_key_tap(backend, "3", 78)
        self.assertEqual(backend.calls, [("key_down", "3"), ("key_up", "3")])


class TestCombatEndProbe(unittest.TestCase):
    def _controller(self):
        return JimoshouAxisController(_FakeTask())

    def test_after_event_only_probes_release_followed_by_long_idle(self):
        controller = self._controller()
        calls = []
        controller._probe_combat_state = lambda: calls.append("probe")

        controller._after_raw_event(
            RawInputEvent("mouse", "left", "down", COMBAT_PROBE_MIN_IDLE_MS)
        )
        controller._after_raw_event(
            RawInputEvent("mouse", "left", "up", COMBAT_PROBE_MIN_IDLE_MS - 1)
        )
        self.assertEqual(calls, [])

        controller._after_raw_event(
            RawInputEvent("mouse", "left", "up", COMBAT_PROBE_MIN_IDLE_MS)
        )
        self.assertEqual(calls, ["probe"])

    def test_consecutive_health_bar_misses_abort_conservatively(self):
        controller = self._controller()
        controller.task.health_bar_visible = False

        for _ in range(COMBAT_PROBE_MISS_LIMIT - 1):
            controller._probe_combat_state()

        with self.assertRaises(RawInputAborted):
            controller._probe_combat_state()
        self.assertEqual(controller.task.next_frame_calls, COMBAT_PROBE_MISS_LIMIT)

    def test_visible_health_bar_resets_miss_streak(self):
        controller = self._controller()
        controller.task.health_bar_visible = False
        controller._probe_combat_state()
        controller._probe_combat_state()
        self.assertEqual(controller._combat_probe_misses, 2)

        controller.task.health_bar_visible = True
        controller._probe_combat_state()
        self.assertEqual(controller._combat_probe_misses, 0)

    def test_explicit_scene_out_of_combat_aborts_immediately(self):
        controller = self._controller()
        controller.task.scene.value = False
        with self.assertRaises(RawInputAborted):
            controller._probe_combat_state()

    def test_combat_end_condition_aborts_without_sending_input(self):
        controller = self._controller()
        controller.task.combat_end_condition = lambda: True
        with self.assertRaises(RawInputAborted):
            controller._probe_combat_state()
        self.assertEqual(controller.task.next_frame_calls, 0)


if __name__ == "__main__":
    unittest.main()
