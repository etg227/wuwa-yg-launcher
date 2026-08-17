import threading
import time
import unittest

from src.axis.AxisChart import OutputBinding
from src.axis.AxisRunner import AxisEvent
from src.axis.CombatMonitor import CombatMonitor


def make_event(move_id="skill"):
    return AxisEvent(0, 2, 0, "tap", OutputBinding("key", "e"), 0, "动作", move_id)


def wait_until(condition, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return condition()


class TestCombatMonitor(unittest.TestCase):
    def make_monitor(self, state, **kwargs):
        options = {
            "confirm_lost_s": 0.03,
            "max_wait_s": 10.0,
            "poll_interval_s": 0.005,
            "suppress_after_move": {},
        }
        options.update(kwargs)
        monitor = CombatMonitor(
            lambda: None,
            lambda: state["target"],
            lambda: state.get("reacquire", False),
            state.setdefault("stop_event", threading.Event()),
            status_callback=state.setdefault("messages", []).append,
            **options,
        )
        self.addCleanup(monitor.stop)
        monitor.start()
        return monitor

    def test_not_armed_before_first_target_never_holds(self):
        state = {"target": False}
        monitor = self.make_monitor(state)

        time.sleep(0.1)

        self.assertTrue(monitor.allow(make_event()))
        self.assertEqual(state["messages"], [])

    def test_confirmed_loss_holds_and_reacquire_resumes(self):
        state = {"target": True}
        monitor = self.make_monitor(state)
        self.assertTrue(wait_until(lambda: monitor._armed))

        state["target"] = False
        self.assertTrue(wait_until(lambda: not monitor.allow(make_event())))
        self.assertIn("目标丢失，暂停时间轴等待新目标", state["messages"])

        state["reacquire"] = True
        self.assertTrue(wait_until(lambda: monitor.allow(make_event())))
        self.assertIn("已重新锁定目标，继续时间轴", state["messages"])

    def test_brief_loss_below_confirm_window_does_not_hold(self):
        state = {"target": True}
        monitor = self.make_monitor(state, confirm_lost_s=0.5)
        self.assertTrue(wait_until(lambda: monitor._armed))

        state["target"] = False
        time.sleep(0.05)
        state["target"] = True
        time.sleep(0.05)

        self.assertTrue(monitor.allow(make_event()))

    def test_timeout_continue_policy_reopens_gate(self):
        state = {"target": True}
        monitor = self.make_monitor(state, max_wait_s=0.05)
        self.assertTrue(wait_until(lambda: monitor._armed))

        state["target"] = False
        self.assertTrue(wait_until(lambda: not monitor.allow(make_event())))
        self.assertTrue(wait_until(lambda: monitor.allow(make_event())))

        self.assertIn("等待新目标超时，继续按时间轴执行", state["messages"])
        self.assertFalse(state["stop_event"].is_set())

    def test_timeout_stop_policy_sets_stop_event(self):
        state = {"target": True}
        monitor = self.make_monitor(state, max_wait_s=0.05, stop_on_timeout=True)
        self.assertTrue(wait_until(lambda: monitor._armed))

        state["target"] = False
        self.assertTrue(wait_until(state["stop_event"].is_set))
        self.assertIn("等待新目标超时，停止播放", state["messages"])

    def test_suppress_window_ignores_loss_after_big_animation(self):
        state = {"target": True}
        monitor = self.make_monitor(state, suppress_after_move={"liberation": 5.0})
        self.assertTrue(wait_until(lambda: monitor._armed))

        self.assertTrue(monitor.allow(make_event("liberation")))
        state["target"] = False
        time.sleep(0.1)

        self.assertTrue(monitor.allow(make_event()))

    def test_blocked_frame_refresh_fails_open(self):
        blocker = threading.Event()
        state = {"target": True, "blocked": False}

        def refresh():
            if state["blocked"]:
                blocker.wait()

        stop_event = threading.Event()
        messages = []
        monitor = CombatMonitor(
            refresh,
            lambda: state["target"],
            lambda: False,
            stop_event,
            confirm_lost_s=0.03,
            poll_interval_s=0.005,
            stale_after_s=0.1,
            suppress_after_move={},
            status_callback=messages.append,
        )
        self.addCleanup(blocker.set)
        self.addCleanup(monitor.stop)
        monitor.start()
        self.assertTrue(wait_until(lambda: monitor._armed))

        state["target"] = False
        self.assertTrue(wait_until(lambda: not monitor.allow(make_event())))

        # 取帧线程卡死后采样停止更新，闸门必须自动放行避免卡死时间轴。
        state["blocked"] = True
        self.assertTrue(wait_until(lambda: monitor.allow(make_event())))

    def test_stop_joins_monitor_thread(self):
        state = {"target": True}
        monitor = self.make_monitor(state)
        self.assertTrue(wait_until(lambda: monitor.is_alive))

        monitor.stop()

        self.assertFalse(monitor.is_alive)

    def test_stop_during_reacquire_exits_after_call_returns(self):
        reacquire_started = threading.Event()
        release_reacquire = threading.Event()
        stop_event = threading.Event()
        target = {"found": True}

        def reacquire():
            reacquire_started.set()
            release_reacquire.wait(1.0)
            return False

        monitor = CombatMonitor(
            lambda: None,
            lambda: target["found"],
            reacquire,
            stop_event,
            confirm_lost_s=0.01,
            poll_interval_s=0.005,
            suppress_after_move={},
        )
        self.addCleanup(release_reacquire.set)
        self.addCleanup(monitor.stop)
        monitor.start()
        self.assertTrue(wait_until(lambda: monitor._armed))
        target["found"] = False
        self.assertTrue(reacquire_started.wait(1.0))

        stop_event.set()
        monitor.stop(timeout=0.01)
        self.assertTrue(monitor.is_alive)
        release_reacquire.set()

        self.assertTrue(wait_until(lambda: not monitor.is_alive))


if __name__ == "__main__":
    unittest.main()
