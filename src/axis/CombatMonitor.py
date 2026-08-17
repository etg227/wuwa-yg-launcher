import threading
import time
from collections.abc import Callable

# 这些动作的演出会临时隐藏目标 UI，动作触发后的一段时间内不判定目标丢失。
SUPPRESS_AFTER_MOVE = {
    "liberation": 4.0,
    "switch_1": 2.0,
    "switch_2": 2.0,
    "switch_3": 2.0,
}


class CombatMonitor:
    """后台监测目标锁定状态，为时间轴提供转火/boss 刷新空档的暂停闸门。

    识别只在监测线程执行，时间轴线程通过 allow 读取结果。闸门只有在
    本场至少锁定过一次目标之后才会武装，避免挑战开始前的无目标阶段误暂停；
    识别异常或采样停滞时闸门保持放行，监测故障不会卡死播放。

    实例与单次播放绑定。stop 后保留线程引用和已设置的取消状态，禁止将同一
    实例用于下一次播放；新的播放应创建新的监测器。
    """

    def __init__(
        self,
        refresh_frame: Callable[[], object],
        has_target: Callable[[], bool],
        reacquire_target: Callable[[], bool],
        stop_event: threading.Event,
        *,
        confirm_lost_s: float = 0.8,
        max_wait_s: float = 30.0,
        stop_on_timeout: bool = False,
        poll_interval_s: float = 0.15,
        stale_after_s: float = 5.0,
        suppress_after_move: dict[str, float] | None = None,
        clock: Callable[[], float] = time.monotonic,
        status_callback: Callable[[str], None] | None = None,
    ):
        self._refresh_frame = refresh_frame
        self._has_target = has_target
        self._reacquire_target = reacquire_target
        self._stop_event = stop_event
        self._confirm_lost_s = confirm_lost_s
        self._max_wait_s = max_wait_s
        self._stop_on_timeout = stop_on_timeout
        self._poll_interval_s = poll_interval_s
        self._stale_after_s = stale_after_s
        self._suppress_after_move = SUPPRESS_AFTER_MOVE if suppress_after_move is None else suppress_after_move
        self._clock = clock
        self._status_callback = status_callback
        self._cancelled = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._thread = None
        self._armed = False
        self._holding = False
        self._gave_up = False
        self._lost_since = None
        self._hold_started = 0.0
        self._suppress_until = 0.0
        self._last_sample = None

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._run, name="AxisCombatMonitor", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        self._cancelled.set()
        with self._lifecycle_lock:
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout))

    @property
    def is_alive(self) -> bool:
        with self._lifecycle_lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def gave_up(self) -> bool:
        """目标消失且等待超时；循环播放据此判定战斗结束。"""
        return self._gave_up

    def allow(self, event) -> bool:
        """时间轴线程在执行每个事件前调用；False 表示暂停等待。"""
        suppress = self._suppress_after_move.get(event.move_id)
        if suppress:
            self._suppress_until = max(self._suppress_until, self._clock() + suppress)
        if not self._holding:
            return True
        last_sample = self._last_sample
        if last_sample is None or self._clock() - last_sample > self._stale_after_s:
            # 采样线程停滞（例如取帧阻塞），放行以免卡死时间轴。
            return True
        return False

    def _run(self) -> None:
        while not self._cancelled.is_set() and not self._stop_event.is_set():
            found = self._sample()
            if found is not None:
                now = self._clock()
                self._last_sample = now
                self._apply_sample(found, now)
            if self._cancelled.wait(self._poll_interval_s):
                return

    def _sample(self):
        try:
            self._refresh_frame()
            if self._cancelled.is_set() or self._stop_event.is_set():
                return None
            return bool(self._has_target())
        except Exception:
            # 单次识别失败不改变状态；持续失败会触发 allow 的停滞放行。
            return None

    def _apply_sample(self, found: bool, now: float) -> None:
        if found:
            self._armed = True
            self._lost_since = None
            self._gave_up = False
            if self._holding:
                self._holding = False
                self._notify("已重新锁定目标，继续时间轴")
            return
        if not self._armed or self._gave_up or now < self._suppress_until:
            self._lost_since = None
            return
        if self._lost_since is None:
            self._lost_since = now
            return
        if not self._holding:
            if now - self._lost_since >= self._confirm_lost_s:
                self._holding = True
                self._hold_started = now
                self._notify("目标丢失，暂停时间轴等待新目标")
            return
        if now - self._hold_started >= self._max_wait_s:
            if self._stop_on_timeout:
                self._notify("等待新目标超时，停止播放")
                self._stop_event.set()
            else:
                self._gave_up = True
                self._holding = False
                self._notify("等待新目标超时，继续按时间轴执行")
            return
        try:
            reacquired = self._reacquire_target()
        except Exception:
            reacquired = False
        # 重新索敌内部会阻塞数秒，结束后刷新采样时间避免误判停滞。
        self._last_sample = self._clock()
        if reacquired:
            self._holding = False
            self._lost_since = None
            self._notify("已重新锁定目标，继续时间轴")

    def _notify(self, message: str) -> None:
        if self._status_callback:
            try:
                self._status_callback(message)
            except Exception:
                pass
