import unittest

from src.combat.RawInputTimeline import (
    RawInputAborted,
    RawInputEvent,
    RawInputTimelineRunner,
    compile_raw_timeline,
)


class FakeBackend:
    def __init__(self):
        self.calls = []

    def key_down(self, code):
        self.calls.append(("key_down", code))

    def key_up(self, code):
        self.calls.append(("key_up", code))

    def mouse_down(self, button):
        self.calls.append(("mouse_down", button))

    def mouse_up(self, button):
        self.calls.append(("mouse_up", button))


class FakeClock:
    def __init__(self):
        self.now = 0

    def clock_ns(self):
        # 每次查询推进 0.1ms，足够让 runner 的短自旋自然结束。
        self.now += 100_000
        return self.now

    def sleep(self, seconds):
        self.now += int(seconds * 1_000_000_000)


class TestRawInputTimeline(unittest.TestCase):
    def test_compile_uses_delay_after_as_absolute_deadline(self):
        events = (
            RawInputEvent("key", "3", "down", 100),
            RawInputEvent("key", "3", "up", 100),
            RawInputEvent("mouse", "left", "down", 78),
            RawInputEvent("mouse", "left", "up", 450),
        )
        self.assertEqual([item.at_ms for item in compile_raw_timeline(events)], [0, 100, 200, 278])

    def test_runner_preserves_explicit_down_up_order(self):
        events = (
            RawInputEvent("key", "r", "down", 78),
            RawInputEvent("key", "r", "up", 20),
            RawInputEvent("mouse", "left", "down", 50),
            RawInputEvent("mouse", "left", "up", 0),
        )
        backend = FakeBackend()
        clock = FakeClock()
        stats = RawInputTimelineRunner(clock_ns=clock.clock_ns, sleep=clock.sleep).run(events, backend)
        self.assertEqual(
            backend.calls,
            [
                ("key_down", "r"),
                ("key_up", "r"),
                ("mouse_down", "left"),
                ("mouse_up", "left"),
            ],
        )
        self.assertEqual(stats.event_count, 4)

    def test_runner_releases_pressed_input_when_backend_raises(self):
        class RaisingBackend(FakeBackend):
            def key_up(self, code):
                self.calls.append(("key_up", code))
                if len(self.calls) == 2:
                    raise RuntimeError("boom")

        events = (
            RawInputEvent("key", "e", "down", 10),
            RawInputEvent("key", "e", "up", 0),
        )
        backend = RaisingBackend()
        clock = FakeClock()
        with self.assertRaises(RuntimeError):
            RawInputTimelineRunner(clock_ns=clock.clock_ns, sleep=clock.sleep).run(events, backend)
        # finally 会再次尝试释放仍被 runner 视为按下的 E。
        self.assertEqual(backend.calls[-1], ("key_up", "e"))

    def test_abort_stops_timeline_and_releases_pressed_input(self):
        # R 按下之后停止请求生效：runner 必须抛 RawInputAborted，
        # 不再发送后续事件，并在退出前释放仍按住的 R。
        aborted = {"flag": False}
        events = (
            RawInputEvent("key", "r", "down", 100),
            RawInputEvent("key", "r", "up", 5000),
            RawInputEvent("key", "e", "down", 20),
            RawInputEvent("key", "e", "up", 0),
        )

        backend = FakeBackend()
        clock = FakeClock()

        original_key_down = backend.key_down

        def key_down_then_abort(code):
            original_key_down(code)
            aborted["flag"] = True

        backend.key_down = key_down_then_abort

        runner = RawInputTimelineRunner(
            clock_ns=clock.clock_ns,
            sleep=clock.sleep,
            should_abort=lambda: aborted["flag"],
        )
        with self.assertRaises(RawInputAborted):
            runner.run(events, backend)

        self.assertEqual(backend.calls[0], ("key_down", "r"))
        self.assertEqual(backend.calls[-1], ("key_up", "r"))
        self.assertNotIn(("key_down", "e"), backend.calls)

    def test_abort_polling_caps_long_sleeps(self):
        # 长等待必须被切成 ABORT_POLL_S 以内的片段，停止请求才不会等满整段。
        sleeps = []

        class PollClock(FakeClock):
            def sleep(self, seconds):
                sleeps.append(seconds)
                super().sleep(seconds)

        events = (
            RawInputEvent("key", "q", "down", 3000),
            RawInputEvent("key", "q", "up", 0),
        )
        clock = PollClock()
        runner = RawInputTimelineRunner(
            clock_ns=clock.clock_ns,
            sleep=clock.sleep,
            should_abort=lambda: False,
        )
        runner.run(events, FakeBackend())
        self.assertTrue(sleeps)
        self.assertLessEqual(max(sleeps), RawInputTimelineRunner.ABORT_POLL_S)

    def test_no_abort_callback_keeps_single_long_sleep(self):
        # 不传 should_abort 时保持原行为：一次 sleep 睡满剩余时间，不做轮询切分。
        sleeps = []

        class PollClock(FakeClock):
            def sleep(self, seconds):
                sleeps.append(seconds)
                super().sleep(seconds)

        events = (
            RawInputEvent("key", "q", "down", 3000),
            RawInputEvent("key", "q", "up", 0),
        )
        clock = PollClock()
        RawInputTimelineRunner(clock_ns=clock.clock_ns, sleep=clock.sleep).run(
            events, FakeBackend()
        )
        self.assertTrue(any(duration > 1.0 for duration in sleeps))


if __name__ == "__main__":
    unittest.main()
