import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from src.axis.AxisChart import AxisChart, OutputBinding

MAX_AXIS_EVENTS = 100000


class AxisOutput(Protocol):
    def tap(self, binding: OutputBinding) -> None: ...

    def press(self, binding: OutputBinding) -> None: ...

    def release(self, binding: OutputBinding) -> None: ...


@dataclass(order=True, frozen=True)
class AxisEvent:
    at_ms: float
    priority: int
    sequence: int
    operation: str = field(compare=False)
    binding: OutputBinding = field(compare=False)
    step_index: int = field(compare=False)
    label: str = field(compare=False)
    move_id: str = field(compare=False, default="")


def build_axis_events(
    chart: AxisChart,
    mappings: dict[str, OutputBinding | None],
    repeat_interval_ms: int = 110,
    include_start_trigger: bool = True,
) -> tuple[AxisEvent, ...]:
    """把语义动作展开成可并发执行的按下、释放和轻触事件。"""

    if repeat_interval_ms < 30 or repeat_interval_ms > 1000:
        raise ValueError("普攻连点间隔必须在 30～1000 毫秒之间")

    events = []
    sequence = 0

    def append_event(event: AxisEvent) -> None:
        if len(events) >= MAX_AXIS_EVENTS:
            raise ValueError(f"展开后的按键事件超过上限 {MAX_AXIS_EVENTS}")
        events.append(event)

    if include_start_trigger and chart.start_trigger_move_id:
        move_id = chart.start_trigger_move_id
        if binding := mappings.get(move_id):
            append_event(AxisEvent(0, 2, sequence, "tap", binding, -1, chart.label_for(move_id), move_id))
            sequence += 1

    for step_index, step in enumerate(chart.steps):
        binding = mappings.get(step.move_id)
        if binding is None:
            continue
        if binding.mode == "repeat":
            offset = 0.0
            while offset < max(step.duration_ms, 1):
                append_event(
                    AxisEvent(
                        step.start_ms + offset,
                        2,
                        sequence,
                        "tap",
                        binding,
                        step_index,
                        step.label,
                        step.move_id,
                    )
                )
                sequence += 1
                offset += repeat_interval_ms
        elif binding.mode == "hold":
            append_event(
                AxisEvent(step.start_ms, 1, sequence, "down", binding, step_index, step.label, step.move_id)
            )
            sequence += 1
            release_at = step.start_ms + max(step.duration_ms, 40)
            append_event(
                AxisEvent(release_at, 0, sequence, "up", binding, step_index, step.label, step.move_id)
            )
            sequence += 1
        else:
            append_event(
                AxisEvent(step.start_ms, 2, sequence, "tap", binding, step_index, step.label, step.move_id)
            )
            sequence += 1
    return tuple(sorted(events))


class AxisRunner:
    """基于单调时钟执行时间轴，并保证停止时释放全部长按输入。"""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock

    def run(
        self,
        events: tuple[AxisEvent, ...],
        output: AxisOutput,
        stop_event: threading.Event,
        speed: float = 1.0,
        action_callback: Callable[[AxisEvent], None] | None = None,
        progress_callback: Callable[[float], None] | None = None,
        sync_callback: Callable[[AxisEvent], bool] | None = None,
        timing_callback: Callable[[AxisEvent, float, float, float], None] | None = None,
        gate_callback: Callable[[AxisEvent], bool] | None = None,
    ) -> bool:
        if speed <= 0:
            raise ValueError("播放速度必须大于 0")

        held: dict[OutputBinding, int] = {}
        notified_steps = set()
        start = self.clock()
        timeline_shift = 0.0
        total_ms = max((event.at_ms for event in events), default=0.0)
        timing_count = 0
        timing_abs_total = 0.0
        timing_abs_max = 0.0
        cancelled = False
        try:
            for event in events:
                if gate_callback and not gate_callback(event):
                    # 闸门关闭（例如转火空档）：先释放长按，暂停到闸门重新放行，
                    # 等待时间计入时间轴偏移，后续动作不会集中补发。
                    gate_started = self.clock()
                    self._release_all(output, held)
                    while not gate_callback(event):
                        if stop_event.wait(0.05):
                            cancelled = True
                            break
                    if cancelled:
                        break
                    timeline_shift += self.clock() - gate_started
                target = start + event.at_ms / 1000 / speed + timeline_shift
                remaining = target - self.clock()
                if remaining > 0 and stop_event.wait(remaining):
                    cancelled = True
                    break
                if stop_event.is_set():
                    cancelled = True
                    break

                drift_ms = (self.clock() - target) * 1000
                timing_count += 1
                timing_abs_total += abs(drift_ms)
                timing_abs_max = max(timing_abs_max, abs(drift_ms))
                if timing_callback:
                    timing_callback(
                        event,
                        drift_ms,
                        timing_abs_total / timing_count,
                        timing_abs_max,
                    )

                if event.step_index not in notified_steps:
                    notified_steps.add(event.step_index)
                    if action_callback:
                        action_callback(event)
                self._execute_event(event, output, held)

                if sync_callback:
                    sync_started = self.clock()
                    if sync_callback(event):
                        timeline_shift += max(0.0, self.clock() - sync_started)
                    if stop_event.is_set():
                        cancelled = True
                        break

                if progress_callback:
                    progress_callback(100.0 if total_ms <= 0 else min(100.0, event.at_ms / total_ms * 100))
        finally:
            self._release_all(output, held)
        if progress_callback and not cancelled:
            progress_callback(100.0)
        return cancelled

    @staticmethod
    def _release_all(output: AxisOutput, held: dict[OutputBinding, int]) -> None:
        for binding in reversed(tuple(held)):
            try:
                output.release(binding)
            except Exception:
                # 清理阶段不能因为一个键释放失败而漏掉其他键。
                continue
        held.clear()

    @staticmethod
    def _execute_event(event: AxisEvent, output: AxisOutput, held: dict[OutputBinding, int]) -> None:
        binding = event.binding
        if event.operation == "tap":
            output.tap(binding)
        elif event.operation == "down":
            count = held.get(binding, 0)
            if count == 0:
                output.press(binding)
            held[binding] = count + 1
        elif event.operation == "up":
            count = held.get(binding, 0)
            if count <= 1:
                if count == 1:
                    output.release(binding)
                held.pop(binding, None)
            else:
                held[binding] = count - 1
        else:
            raise ValueError(f"未知轴事件：{event.operation}")
