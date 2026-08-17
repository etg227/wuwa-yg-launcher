import threading

from PySide6.QtCore import QObject, Signal

from src.axis.AxisChart import AxisChart, OutputBinding
from src.axis.AxisRunner import AxisEvent, AxisOutput, AxisRunner, build_axis_events
from src.axis.CombatMonitor import CombatMonitor
from src.axis.SequenceRunner import SequenceRunner, build_sequence_steps
from src.axis.VisualSync import verify_switch_async, wait_for_switch_sync
from src.combat.CombatCheck import CombatCheck


class AxisPlaybackSignals(QObject):
    status_changed = Signal(str)
    action_changed = Signal(int, str, str)
    progress_changed = Signal(int)
    timing_changed = Signal(float, float, float)
    playback_finished = Signal(bool, str)


class InteractionAxisOutput(AxisOutput):
    """直接使用 OK-Script 输入后端，确保停止清理不受任务状态影响。"""

    def __init__(self, interaction):
        self.interaction = interaction

    def tap(self, binding: OutputBinding) -> None:
        if binding.kind == "mouse":
            self.interaction.click(-1, -1, move=False, down_time=0.015, key=binding.code)
        else:
            self.interaction.send_key(binding.code, 0.02)

    def press(self, binding: OutputBinding) -> None:
        if binding.kind == "mouse":
            self.interaction.mouse_down(-1, -1, key=binding.code)
        else:
            self.interaction.send_key_down(binding.code)

    def release(self, binding: OutputBinding) -> None:
        if binding.kind == "mouse":
            self.interaction.mouse_up(key=binding.code)
        else:
            self.interaction.send_key_up(binding.code)


class AxisPlaybackTask(CombatCheck):
    """由“椰果启动器”页面配置并加入统一任务队列的隐藏任务。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "椰果启动器"
        self.description = "按 WWCOMBO 时间线启动角色连段"
        self.visible = False
        self.signals = AxisPlaybackSignals()
        self._settings_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._playback_settings = None
        self._visual_sync = False
        self._sync_timeout = 1.5
        self._pause_on_target_loss = False
        self._target_loss_max_wait = 30.0
        self._target_loss_timeout_stop = False
        self._pause_auto_combat_after = False
        self._sequence_mode = False
        self._basic_interval_ms = 450
        self._repeat_interval_ms = 110
        self._loop_playback = False
        self._loop_start_step = 1
        self._last_timing = None

    def configure_playback(
        self,
        chart: AxisChart,
        mappings: dict[str, OutputBinding | None],
        speed: float,
        countdown: int,
        repeat_interval_ms: int,
        include_start_trigger: bool,
        visual_sync: bool = False,
        sync_timeout: float = 1.5,
        pause_on_target_loss: bool = False,
        target_loss_max_wait: float = 30.0,
        target_loss_timeout_stop: bool = False,
        pause_auto_combat_after: bool = False,
        sequence_mode: bool = False,
        basic_interval_ms: int = 450,
        loop_playback: bool = False,
        loop_start_step: int = 1,
    ) -> None:
        if self.running or self.enabled:
            raise RuntimeError("已有椰果启动器任务正在执行或等待执行")
        events = build_axis_events(chart, mappings, repeat_interval_ms, include_start_trigger)
        sequence_steps = build_sequence_steps(chart, mappings)
        if sequence_mode:
            if not sequence_steps:
                raise ValueError("这个轴没有可推进执行的已识别动作")
            if loop_playback and not pause_on_target_loss:
                raise ValueError("循环播放必须开启目标丢失暂停，用于判断战斗结束")
        elif not events:
            raise ValueError("这个轴没有可执行的已识别动作")
        with self._settings_lock:
            self._playback_settings = (chart, events, sequence_steps, float(speed), int(countdown))
            self._sequence_mode = bool(sequence_mode)
            self._basic_interval_ms = min(2000, max(100, int(basic_interval_ms)))
            self._repeat_interval_ms = int(repeat_interval_ms)
            self._loop_playback = bool(loop_playback)
            self._loop_start_step = max(1, int(loop_start_step))
            self._visual_sync = bool(visual_sync)
            self._sync_timeout = max(0.2, float(sync_timeout))
            self._pause_on_target_loss = bool(pause_on_target_loss)
            self._target_loss_max_wait = max(5.0, float(target_loss_max_wait))
            self._target_loss_timeout_stop = bool(target_loss_timeout_stop)
            self._pause_auto_combat_after = bool(pause_auto_combat_after)
        self._stop_event.clear()
        self._last_timing = None

    def request_stop(self) -> None:
        self._stop_event.set()
        if self.enabled and not self.running:
            self.disable()
            self.signals.playback_finished.emit(True, "已从任务队列移除")

    def run(self):
        with self._settings_lock:
            settings = self._playback_settings
        if settings is None:
            raise RuntimeError("尚未配置椰果启动器")
        chart, events, sequence_steps, speed, countdown = settings

        try:
            for remaining in range(countdown, 0, -1):
                self.signals.status_changed.emit(f"{remaining} 秒后开始，请切回游戏")
                if self._stop_event.wait(1):
                    self.signals.playback_finished.emit(True, "已停止")
                    return

            interaction = self.executor.interaction
            if interaction is None:
                raise RuntimeError("游戏输入设备尚未连接")
            interaction.on_run()
            # 执行器单线程：播放期间触发任务不会运行，自动战斗只在启动前和结束后有输入。
            auto_combat = self._find_auto_combat()
            auto_combat_active = bool(auto_combat is not None and auto_combat.enabled)
            monitor = None
            if self._pause_on_target_loss:
                monitor = CombatMonitor(
                    self.next_frame,
                    self.has_target,
                    lambda: bool(self.target_enemy(wait=True)),
                    self._stop_event,
                    max_wait_s=self._target_loss_max_wait,
                    stop_on_timeout=self._target_loss_timeout_stop,
                    status_callback=self.signals.status_changed.emit,
                )
                monitor.start()
            mode_text = "推进模式" if self._sequence_mode else "时间轴模式"
            title_suffix = "｜自动战斗已让位" if auto_combat_active else ""
            self.signals.status_changed.emit(f"正在执行：{chart.title}｜{mode_text}{title_suffix}")
            loops_done = 0
            try:
                if self._sequence_mode:
                    cancelled, loops_done = SequenceRunner().run(
                        sequence_steps,
                        InteractionAxisOutput(interaction),
                        self._stop_event,
                        basic_interval_ms=self._basic_interval_ms,
                        repeat_interval_ms=self._repeat_interval_ms,
                        speed=speed,
                        loop=self._loop_playback,
                        loop_start_step=self._loop_start_step - 1,
                        should_continue_loop=(lambda: not monitor.gave_up) if monitor else None,
                        gate_callback=monitor.allow if monitor else None,
                        on_switch=self._on_sequence_switch if self._visual_sync else None,
                        action_callback=self._on_action,
                        progress_callback=lambda value: self.signals.progress_changed.emit(round(value)),
                        status_callback=self.signals.status_changed.emit,
                    )
                else:
                    cancelled = AxisRunner().run(
                        events,
                        InteractionAxisOutput(interaction),
                        self._stop_event,
                        speed=speed,
                        action_callback=self._on_action,
                        progress_callback=lambda value: self.signals.progress_changed.emit(round(value)),
                        sync_callback=self._sync_after_switch if self._visual_sync else None,
                        timing_callback=self._on_timing,
                        gate_callback=monitor.allow if monitor else None,
                    )
            finally:
                if monitor is not None:
                    monitor.stop()
            message = "已停止并释放全部按键" if cancelled else "椰果启动器执行完成"
            if self._sequence_mode and loops_done > 1:
                message += f"｜共执行 {loops_done} 轮"
            if self._last_timing is not None:
                _, average_ms, max_ms = self._last_timing
                message += f"｜平均偏差 {average_ms:.1f} ms，最大 {max_ms:.1f} ms"
            if auto_combat_active:
                if self._pause_auto_combat_after:
                    auto_combat.disable()
                    message += "｜已暂停自动战斗"
                else:
                    message += "｜自动战斗接管后续战斗"
            self.signals.playback_finished.emit(cancelled, message)
        except Exception as error:
            self.signals.playback_finished.emit(True, f"执行失败：{error}")
            raise
        finally:
            with self._settings_lock:
                self._playback_settings = None

    def _find_auto_combat(self):
        for task in getattr(self.executor, "trigger_tasks", ()):
            if type(task).__name__ == "AutoCombatTask":
                return task
        return None

    def on_destroy(self):
        self._stop_event.set()

    def _on_action(self, event: AxisEvent) -> None:
        self.signals.action_changed.emit(event.step_index, event.label, event.binding.display_text)

    def _on_timing(self, _event: AxisEvent, current_ms: float, average_ms: float, max_ms: float) -> None:
        self._last_timing = (current_ms, average_ms, max_ms)
        self.signals.timing_changed.emit(current_ms, average_ms, max_ms)

    def _on_sequence_switch(self, step) -> None:
        """切人后不阻塞衔接：后台校验槽位，确认失败补按一次。"""
        expected_slot = int(step.move_id[-1]) - 1
        binding = step.binding

        def retry():
            interaction = self.executor.interaction
            if interaction is None or self._stop_event.is_set():
                return
            self.signals.status_changed.emit(f"切人 {expected_slot + 1} 未确认，已补按")
            if binding.kind == "mouse":
                interaction.click(-1, -1, move=False, down_time=0.015, key=binding.code)
            else:
                interaction.send_key(binding.code, 0.02)

        verify_switch_async(
            self.next_frame,
            self.in_team,
            expected_slot,
            self._stop_event,
            self._sync_timeout,
            retry,
        )

    def _sync_after_switch(self, event: AxisEvent) -> bool:
        if event.operation != "tap" or event.move_id not in {"switch_1", "switch_2", "switch_3"}:
            return False

        expected_slot = int(event.move_id[-1]) - 1
        synced = wait_for_switch_sync(
            self.next_frame,
            self.in_team,
            expected_slot,
            self._stop_event,
            self._sync_timeout,
        )

        if not synced and not self._stop_event.is_set():
            self.signals.status_changed.emit(
                f"切人视觉同步超时：{event.move_id}，继续按时间轴执行"
            )
        # 这个事件仍然是同步点；把等待时间计入时间轴，避免后续动作集中补发。
        return True
