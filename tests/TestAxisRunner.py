import threading
import unittest

from src.axis.AxisChart import AxisChart, OutputBinding
from src.axis.AxisRunner import AxisEvent, AxisRunner, build_axis_events
from tests.TestAxisChart import create_axis_payload


class FakeOutput:
    def __init__(self, fail_on_tap=False):
        self.actions = []
        self.fail_on_tap = fail_on_tap

    def tap(self, binding):
        self.actions.append(("tap", binding.config_text))
        if self.fail_on_tap:
            raise RuntimeError("模拟输出失败")

    def press(self, binding):
        self.actions.append(("down", binding.config_text))

    def release(self, binding):
        self.actions.append(("up", binding.config_text))


class TestAxisRunner(unittest.TestCase):
    def test_event_builder_expands_repeat_and_hold_without_serializing_steps(self):
        chart = AxisChart.from_dict(create_axis_payload())
        mappings = {
            "start_challenge": OutputBinding("key", "f"),
            "skill": OutputBinding("mouse", "left", "repeat"),
            "dodge_hold": OutputBinding("key", "lshift", "hold"),
        }

        events = build_axis_events(chart, mappings, repeat_interval_ms=30)

        self.assertEqual(events[0].binding.config_text, "f")
        self.assertEqual([event.operation for event in events if event.step_index == 1], ["down", "up"])
        repeat_events = [event for event in events if event.step_index == 0]
        self.assertEqual(len(repeat_events), 2)
        self.assertEqual(repeat_events[0].at_ms, 123.5)
        self.assertEqual(repeat_events[0].move_id, "skill")

    def test_runner_releases_held_key_when_later_output_fails(self):
        hold = OutputBinding("key", "lshift", "hold")
        tap = OutputBinding("key", "e")
        chart = AxisChart.from_dict(create_axis_payload())
        events = build_axis_events(
            chart,
            {"start_challenge": None, "skill": tap, "dodge_hold": hold},
            include_start_trigger=False,
        )
        # 把长按提前到第一个动作，确保后续轻触失败时进入清理路径。
        events = tuple(
            sorted(
                [
                    events[-2].__class__(0, 1, 0, "down", hold, 0, "长按"),
                    events[0].__class__(1, 2, 1, "tap", tap, 1, "技能"),
                ]
            )
        )
        output = FakeOutput(fail_on_tap=True)

        with self.assertRaises(RuntimeError):
            AxisRunner().run(events, output, threading.Event(), speed=100)

        self.assertEqual(output.actions, [("down", "lshift:hold"), ("tap", "e"), ("up", "lshift:hold")])

    def test_runner_reports_timing_and_calls_sync_hook(self):
        chart = AxisChart.from_dict(create_axis_payload())
        mappings = {
            "start_challenge": None,
            "skill": OutputBinding("key", "e"),
            "dodge_hold": OutputBinding("key", "lshift", "hold"),
        }
        events = build_axis_events(chart, mappings, include_start_trigger=False)
        output = FakeOutput()
        timing = []
        synced = []

        AxisRunner().run(
            events,
            output,
            threading.Event(),
            speed=100,
            sync_callback=lambda event: synced.append(event.move_id) or False,
            timing_callback=lambda event, current, average, maximum: timing.append(
                (event.move_id, current, average, maximum)
            ),
        )

        self.assertEqual(len(timing), len(events))
        self.assertEqual(len(synced), len(events))
        self.assertTrue(all(item[2] >= 0 and item[3] >= 0 for item in timing))

    def test_successful_sync_wait_is_added_to_timeline_shift(self):
        now = [10.0]

        class AdvancingStopEvent:
            @staticmethod
            def wait(seconds):
                now[0] += seconds
                return False

            @staticmethod
            def is_set():
                return False

        class TimedOutput(FakeOutput):
            def tap(self, binding):
                self.actions.append((binding.code, now[0]))

        binding = OutputBinding("key", "e")
        events = (
            AxisEvent(0, 2, 0, "tap", binding, 0, "切人", "switch_2"),
            AxisEvent(100, 2, 1, "tap", binding, 1, "技能", "skill"),
        )
        output = TimedOutput()

        def sync(event):
            if event.move_id == "switch_2":
                now[0] += 0.5
                return True
            return False

        AxisRunner(clock=lambda: now[0]).run(
            events,
            output,
            AdvancingStopEvent(),
            sync_callback=sync,
        )

        self.assertAlmostEqual(output.actions[0][1], 10.0)
        self.assertAlmostEqual(output.actions[1][1], 10.6)

    def test_gate_hold_releases_keys_and_shifts_timeline(self):
        now = [0.0]

        class AdvancingStopEvent:
            @staticmethod
            def wait(seconds):
                now[0] += seconds
                return False

            @staticmethod
            def is_set():
                return False

        hold = OutputBinding("key", "lshift", "hold")
        tap = OutputBinding("key", "e")
        events = (
            AxisEvent(0, 1, 0, "down", hold, 0, "长按", "dodge_hold"),
            AxisEvent(200, 2, 1, "tap", tap, 1, "技能", "skill"),
            AxisEvent(400, 0, 2, "up", hold, 0, "长按", "dodge_hold"),
        )
        gate_checks = []

        def gate(event):
            gate_checks.append(event.move_id)
            # 技能事件前模拟目标丢失：拦住三次后放行。
            return not (event.move_id == "skill" and gate_checks.count("skill") <= 3)

        class TimedOutput(FakeOutput):
            def tap(self, binding):
                self.actions.append(("tap", now[0]))

        output = TimedOutput()
        cancelled = AxisRunner(clock=lambda: now[0]).run(
            events, output, AdvancingStopEvent(), gate_callback=gate
        )

        self.assertFalse(cancelled)
        # 闸门关闭时先释放长按；后续 up 事件不会重复释放。
        self.assertEqual(output.actions[0], ("down", "lshift:hold"))
        self.assertEqual(output.actions[1], ("up", "lshift:hold"))
        self.assertEqual(len(output.actions), 3)
        # 两次 0.05 秒的闸门等待计入时间轴偏移：0.2 + 0.1 = 0.3。
        self.assertAlmostEqual(output.actions[2][1], 0.3)

    def test_stop_while_gated_is_cancelled_and_keys_released(self):
        stop_event = threading.Event()
        hold = OutputBinding("key", "lshift", "hold")
        tap = OutputBinding("key", "e")
        events = (
            AxisEvent(0, 1, 0, "down", hold, 0, "长按", "dodge_hold"),
            AxisEvent(1, 2, 1, "tap", tap, 1, "技能", "skill"),
        )

        def gate(event):
            if event.move_id == "skill":
                stop_event.set()
                return False
            return True

        output = FakeOutput()
        cancelled = AxisRunner().run(events, output, stop_event, speed=100, gate_callback=gate)

        self.assertTrue(cancelled)
        self.assertEqual(output.actions, [("down", "lshift:hold"), ("up", "lshift:hold")])

    def test_gate_releases_all_overlapping_holds_once(self):
        stop_event = threading.Event()
        first = OutputBinding("key", "lshift", "hold")
        second = OutputBinding("mouse", "right", "hold")
        tap = OutputBinding("key", "e")
        events = (
            AxisEvent(0, 1, 0, "down", first, 0, "长按", "first_hold"),
            AxisEvent(0, 2, 1, "down", second, 1, "长按", "second_hold"),
            AxisEvent(1, 3, 2, "tap", tap, 2, "技能", "skill"),
        )
        checks = 0

        def gate(event):
            nonlocal checks
            if event.move_id != "skill":
                return True
            checks += 1
            return checks > 1

        output = FakeOutput()
        cancelled = AxisRunner().run(events, output, stop_event, speed=100, gate_callback=gate)

        self.assertFalse(cancelled)
        self.assertEqual(output.actions.count(("up", "lshift:hold")), 1)
        self.assertEqual(output.actions.count(("up", "mouse:right:hold")), 1)

    def test_stop_during_last_sync_is_reported_as_cancelled(self):
        stop_event = threading.Event()
        binding = OutputBinding("key", "2")
        event = AxisEvent(0, 2, 0, "tap", binding, 0, "切人", "switch_2")

        def sync(_event):
            stop_event.set()
            return True

        cancelled = AxisRunner().run(
            (event,),
            FakeOutput(),
            stop_event,
            sync_callback=sync,
        )

        self.assertTrue(cancelled)


if __name__ == "__main__":
    unittest.main()
