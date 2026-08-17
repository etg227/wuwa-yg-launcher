import threading
import time
from collections.abc import Callable


def verify_switch_async(
    next_frame: Callable[[], object],
    in_team: Callable[[], tuple],
    expected_slot: int,
    stop_event: threading.Event,
    timeout: float,
    on_failed: Callable[[], None],
) -> threading.Thread:
    """后台校验切人结果，不阻塞时间轴；确认失败时调用 on_failed 补按。"""

    def worker() -> None:
        if not wait_for_switch_sync(next_frame, in_team, expected_slot, stop_event, timeout):
            if not stop_event.is_set():
                try:
                    on_failed()
                except Exception:
                    pass

    thread = threading.Thread(
        target=worker, name=f"AxisSwitchVerify-{expected_slot + 1}", daemon=True
    )
    thread.start()
    return thread


def wait_for_switch_sync(
    next_frame: Callable[[], object],
    in_team: Callable[[], tuple],
    expected_slot: int,
    stop_event: threading.Event,
    timeout: float,
) -> bool:
    """等待切人识别成功；取帧即使阻塞也保证调用方能按时返回。"""
    deadline = time.monotonic() + timeout
    synced = threading.Event()
    cancelled = threading.Event()

    def refresh_and_recognize() -> None:
        # 底层取帧极端情况下可能永久阻塞，因此不能在时间轴线程直接调用。
        while not cancelled.is_set() and not stop_event.is_set():
            try:
                next_frame()
                if cancelled.is_set() or stop_event.is_set():
                    return
                is_in_team, current_slot, _ = in_team()
                if is_in_team and current_slot == expected_slot:
                    synced.set()
                    return
            except Exception:
                # 单帧刷新或识别失败不应终止播放；截止前继续尝试。
                pass
            if cancelled.wait(0.03):
                return

    threading.Thread(
        target=refresh_and_recognize,
        name=f"AxisVisualSync-{expected_slot + 1}",
        daemon=True,
    ).start()
    try:
        while not stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if synced.wait(min(0.02, remaining)):
                return not stop_event.is_set()
        return False
    finally:
        cancelled.set()
