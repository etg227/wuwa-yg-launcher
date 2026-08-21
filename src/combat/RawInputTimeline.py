"""用于内置固定轴实验的原始输入时间线执行器。

这个模块刻意不依赖 BaseChar 的 click_resonance/click_liberation/switch_next_char
等 helper。它只负责按照单调时钟的绝对 deadline 调用已经准备好的原始输入后端，
用于验证“鼠标驱动宏的 key-down/key-up 语义”是否能被软件输入层复现。

它不是外部轴格式解析器，也不负责下载、导入或播放第三方轴文件。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class RawInputEvent:
    """一个原始输入事件，以及该事件执行后到下一事件的等待时间。"""

    device: str  # key / mouse
    code: str
    action: str  # down / up
    delay_after_ms: int
    label: str = ""

    def __post_init__(self):
        if self.device not in {"key", "mouse"}:
            raise ValueError(f"unsupported device: {self.device}")
        if self.action not in {"down", "up"}:
            raise ValueError(f"unsupported action: {self.action}")
        if self.delay_after_ms < 0:
            raise ValueError("delay_after_ms must be >= 0")
        if not self.code:
            raise ValueError("code must not be empty")


@dataclass(frozen=True)
class ScheduledRawInput:
    at_ms: int
    event: RawInputEvent


@dataclass(frozen=True)
class RawInputTimingStats:
    event_count: int
    average_abs_drift_ms: float
    max_abs_drift_ms: float


class RawInputAborted(Exception):
    """外部停止请求（F10 停止 / 任务禁用 / 暂停 / 退出）中止了原始输入时间线。"""


class RawInputBackend(Protocol):
    def key_down(self, code: str) -> None: ...

    def key_up(self, code: str) -> None: ...

    def mouse_down(self, button: str) -> None: ...

    def mouse_up(self, button: str) -> None: ...


def compile_raw_timeline(events: Sequence[RawInputEvent]) -> tuple[ScheduledRawInput, ...]:
    """把“事件后等待”转换成从 0 开始的绝对时间点。"""

    at_ms = 0
    scheduled = []
    for event in events:
        scheduled.append(ScheduledRawInput(at_ms=at_ms, event=event))
        at_ms += event.delay_after_ms
    return tuple(scheduled)


class RawInputTimelineRunner:
    """按绝对 deadline 执行原始输入，并在异常/结束时释放仍处于按下状态的输入。"""

    # 最后约 1ms 用短自旋避免普通 sleep 的唤醒误差继续累积；宏段很短，CPU 开销可控。
    SPIN_WINDOW_NS = 1_000_000
    # 提供 should_abort 时，长等待被切成不超过该长度的片段，保证停止请求最迟
    # 在这个间隔内被响应；绝对 deadline 不受影响（每次循环重算剩余时间）。
    ABORT_POLL_S = 0.05

    def __init__(
        self,
        clock_ns=time.monotonic_ns,
        sleep=time.sleep,
        should_abort=None,
        after_event=None,
    ):
        self.clock_ns = clock_ns
        self.sleep = sleep
        self.should_abort = should_abort
        self.after_event = after_event

    def run(self, events: Sequence[RawInputEvent], backend: RawInputBackend) -> RawInputTimingStats:
        schedule = compile_raw_timeline(events)
        if not schedule:
            return RawInputTimingStats(0, 0.0, 0.0)

        start_ns = self.clock_ns()
        pressed_keys: set[str] = set()
        pressed_mouse: set[str] = set()
        drifts = []

        try:
            for scheduled in schedule:
                target_ns = start_ns + scheduled.at_ms * 1_000_000
                self._wait_until(target_ns)
                drift_ms = (self.clock_ns() - target_ns) / 1_000_000
                drifts.append(abs(drift_ms))
                self._execute(scheduled.event, backend, pressed_keys, pressed_mouse)
                if self.after_event is not None:
                    # 回调仍处于同一条绝对时间线上：适合把只应发生在长 idle
                    # 区间里的轻量状态检查塞进已有等待，不需要重新计算相对 sleep。
                    self.after_event(scheduled.event)
        finally:
            self._release_all(backend, pressed_keys, pressed_mouse)

        return RawInputTimingStats(
            event_count=len(drifts),
            average_abs_drift_ms=sum(drifts) / len(drifts),
            max_abs_drift_ms=max(drifts),
        )

    def _wait_until(self, target_ns: int) -> None:
        while True:
            if self.should_abort is not None and self.should_abort():
                # run() 的 finally 会释放仍按下的输入，这里只需要中断等待。
                raise RawInputAborted("停止请求已触发，中止原始输入时间线")
            remaining_ns = target_ns - self.clock_ns()
            if remaining_ns <= 0:
                return
            if remaining_ns > self.SPIN_WINDOW_NS:
                sleep_s = (remaining_ns - self.SPIN_WINDOW_NS) / 1_000_000_000
                if self.should_abort is not None:
                    sleep_s = min(sleep_s, self.ABORT_POLL_S)
                self.sleep(sleep_s)
                continue
            # 短窗口直接自旋；不要调用 helper/next_frame，也不要重新计算相对 sleep。

    @staticmethod
    def _execute(
        event: RawInputEvent,
        backend: RawInputBackend,
        pressed_keys: set[str],
        pressed_mouse: set[str],
    ) -> None:
        if event.device == "key":
            if event.action == "down":
                backend.key_down(event.code)
                pressed_keys.add(event.code)
            else:
                backend.key_up(event.code)
                pressed_keys.discard(event.code)
            return

        if event.action == "down":
            backend.mouse_down(event.code)
            pressed_mouse.add(event.code)
        else:
            backend.mouse_up(event.code)
            pressed_mouse.discard(event.code)

    @staticmethod
    def _release_all(backend: RawInputBackend, pressed_keys: set[str], pressed_mouse: set[str]) -> None:
        for code in tuple(pressed_keys):
            try:
                backend.key_up(code)
            except Exception:
                pass
        pressed_keys.clear()

        for button in tuple(pressed_mouse):
            try:
                backend.mouse_up(button)
            except Exception:
                pass
        pressed_mouse.clear()
