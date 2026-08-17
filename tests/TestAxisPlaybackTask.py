import threading
import time
import unittest

from src.axis.VisualSync import verify_switch_async, wait_for_switch_sync


class TestAxisPlaybackTask(unittest.TestCase):
    def test_visual_sync_succeeds_when_expected_slot_is_recognized(self):
        stop_event = threading.Event()

        started = time.monotonic()
        self.assertTrue(
            wait_for_switch_sync(lambda: None, lambda: (True, 1, None), 1, stop_event, 0.08)
        )

        self.assertLess(time.monotonic() - started, 0.08)

    def test_visual_sync_times_out_and_continues_timeline(self):
        stop_event = threading.Event()

        started = time.monotonic()
        self.assertFalse(
            wait_for_switch_sync(lambda: None, lambda: (True, 0, None), 1, stop_event, 0.06)
        )
        elapsed = time.monotonic() - started

        self.assertGreaterEqual(elapsed, 0.05)
        self.assertLess(elapsed, 0.2)

    def test_visual_sync_stop_interrupts_blocked_frame_refresh(self):
        stop_event = threading.Event()
        frame_block = threading.Event()
        threading.Timer(0.04, stop_event.set).start()

        started = time.monotonic()
        self.assertFalse(
            wait_for_switch_sync(frame_block.wait, lambda: (False, None, None), 1, stop_event, 1.0)
        )

        self.assertLess(time.monotonic() - started, 0.2)

    def test_visual_sync_exception_does_not_escape_or_wait_forever(self):
        stop_event = threading.Event()

        def fail_refresh():
            raise RuntimeError("no frame")

        started = time.monotonic()
        self.assertFalse(
            wait_for_switch_sync(
                fail_refresh,
                lambda: self.fail("recognition must not run after refresh failure"),
                1,
                stop_event,
                0.06,
            )
        )

        self.assertLess(time.monotonic() - started, 0.2)


    def test_async_switch_verify_retries_after_timeout(self):
        stop_event = threading.Event()
        failed = threading.Event()

        thread = verify_switch_async(
            lambda: None, lambda: (True, 0, None), 1, stop_event, 0.05, failed.set
        )
        thread.join(1.0)

        self.assertTrue(failed.is_set())

    def test_async_switch_verify_success_skips_retry(self):
        stop_event = threading.Event()
        failed = threading.Event()

        thread = verify_switch_async(
            lambda: None, lambda: (True, 1, None), 1, stop_event, 0.2, failed.set
        )
        thread.join(1.0)

        self.assertFalse(failed.is_set())


if __name__ == "__main__":
    unittest.main()
