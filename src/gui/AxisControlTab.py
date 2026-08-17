import threading

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, FluentIcon, LineEdit, PrimaryPushButton, PushButton, TableWidget

from ok.gui.util.app import show_info_bar
from ok.gui.widget.CustomTab import CustomTab
from ok.util.config import Config
from src.axis import (
    AxisChart,
    AxisFormatError,
    build_default_output_mapping,
    download_community_chart,
    load_axis_file,
    parse_output_binding,
)
from src.axis.InputMonitor import InputMonitor
from src.axis.TextAxis import parse_text_axis
from src.task.AxisPlaybackTask import AxisPlaybackTask


class AxisImportSignals(QObject):
    imported = Signal(object, str)
    failed = Signal(str)


class AxisControlTab(CustomTab):
    def __init__(self):
        super().__init__()
        self.chart: AxisChart | None = None
        self.playback_task = None
        self.task_signals_connected = False
        self.settings = Config(
            "AxisControlTab",
            {
                "Community Axis": "",
                "Speed": 1.0,
                "Countdown": 3,
                "Repeat Interval": 110,
                "Start Trigger": True,
                "Visual Sync": True,
                "Sync Timeout": 1.5,
                "Target Pause": False,
                "Target Wait": 30,
                "Target Timeout Stop": False,
                "Pause Auto Combat After": False,
                "Sequence Mode": True,
                "Basic Interval": 450,
                "Loop Playback": False,
                "Loop Start": 1,
                "Text Axis": "",
                "Move Mappings": {},
            },
        )
        self.import_signals = AxisImportSignals()
        self.import_signals.imported.connect(self._community_imported)
        self.import_signals.failed.connect(self._community_failed)

        self._build_import_area()
        self._build_chart_area()
        self._build_playback_area()

        self.input_monitor = InputMonitor("F10")
        self.input_monitor.held_changed.connect(self._physical_input_changed)
        self.input_monitor.emergency_stop.connect(self._emergency_stop)
        self.input_monitor.monitor_error.connect(self._monitor_error)
        self.input_monitor.start()

    @property
    def name(self):
        return "椰果启动器"

    @property
    def icon(self):
        return FluentIcon.PLAY

    def showEvent(self, event):
        super().showEvent(event)
        self._connect_playback_task()

    def _build_import_area(self) -> None:
        container = QWidget(self.view)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(BodyLabel("导入 nova.fb520.site 社区轴或本地 .wwcombo.json 文件。"))

        row = QHBoxLayout()
        self.community_input = LineEdit(container)
        self.community_input.setPlaceholderText("粘贴 wwc_... ID、详情链接或下载链接")
        self.community_input.setText(self.settings.get("Community Axis", ""))
        self.community_button = PrimaryPushButton("导入社区轴", container)
        self.community_button.clicked.connect(self._import_community)
        self.local_button = PushButton("打开本地轴", container)
        self.local_button.clicked.connect(self._import_local)
        self.website_button = PushButton("打开轴社区", container)
        self.website_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://nova.fb520.site/"))
        )
        row.addWidget(self.community_input, 1)
        row.addWidget(self.community_button)
        row.addWidget(self.local_button)
        row.addWidget(self.website_button)
        layout.addLayout(row)

        self.chart_summary = BodyLabel("尚未导入椰果启动器轴")
        layout.addWidget(self.chart_summary)
        self.add_card("椰果启动器来源", container)
        self._build_text_axis_area()

    def _build_text_axis_area(self) -> None:
        container = QWidget(self.view)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            BodyLabel(
                "直接输入动作序列，用推进模式执行。语法：1/2/3=切人，a=普攻（a3=三次），"
                "e=共鸣技能（e1.5=长按1.5秒），q=声骸，r=共鸣解放，d=闪避，j=跳跃，"
                "z=重击（z1.2=长按1.2秒），f=处决/交互，w0.5=等待0.5秒，"
                "“循环”=之后的步骤循环播放，#=注释。"
            )
        )
        self.text_axis_edit = QPlainTextEdit(container)
        self.text_axis_edit.setPlaceholderText("示例：\n1 a3 e\n2 e r q\n循环\n3 a e\n1 a2 e r")
        self.text_axis_edit.setPlainText(str(self.settings.get("Text Axis", "")))
        self.text_axis_edit.setMinimumHeight(80)
        self.text_axis_edit.setMaximumHeight(140)
        layout.addWidget(self.text_axis_edit)
        row = QHBoxLayout()
        row.addStretch(1)
        self.text_axis_button = PrimaryPushButton("解析并载入文字轴", container)
        self.text_axis_button.clicked.connect(self._import_text_axis)
        row.addWidget(self.text_axis_button)
        layout.addLayout(row)
        self.add_card("文字轴", container)

    def _import_text_axis(self) -> None:
        text = self.text_axis_edit.toPlainText()
        try:
            chart, loop_start = parse_text_axis(text)
        except AxisFormatError as error:
            self._show_error(str(error))
            return
        self.settings["Text Axis"] = text
        self._load_chart(chart, "文字轴")
        self.sequence_mode_check.setChecked(True)
        if loop_start is not None:
            self.loop_check.setChecked(True)
            self.loop_start_spin.setValue(loop_start + 1)
            self.status_label.setText(
                f"文字轴已载入：循环从第 {loop_start + 1} 步开始，播放到战斗结束"
            )

    def _build_chart_area(self) -> None:
        container = QWidget(self.view)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(BodyLabel("动作映射（双击“实际输出”可修改；格式示例：e、lshift:hold、mouse:left:repeat）"))
        self.mapping_table = TableWidget(container)
        self.mapping_table.setColumnCount(3)
        self.mapping_table.setHorizontalHeaderLabels(["动作", "轴作者按键", "实际输出"])
        self.mapping_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.mapping_table.verticalHeader().hide()
        self.mapping_table.setMinimumHeight(132)
        layout.addWidget(self.mapping_table)

        layout.addWidget(BodyLabel("时间轴预览"))
        self.timeline_table = TableWidget(container)
        self.timeline_table.setColumnCount(5)
        self.timeline_table.setHorizontalHeaderLabels(["时间", "角色", "动作", "持续", "轨道"])
        self.timeline_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # 行号即“循环起点”的步序号，保持可见。
        self.timeline_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.timeline_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.timeline_table.setMinimumHeight(160)
        layout.addWidget(self.timeline_table)
        self.add_card("识别结果", container)

    def _build_playback_area(self) -> None:
        container = QWidget(self.view)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        options = QFormLayout()
        self.speed_spin = QDoubleSpinBox(container)
        self.speed_spin.setRange(0.25, 2.0)
        self.speed_spin.setSingleStep(0.05)
        self.speed_spin.setValue(float(self.settings.get("Speed", 1.0)))
        self.speed_spin.setSuffix(" ×")
        options.addRow("播放速度", self.speed_spin)

        self.countdown_spin = QSpinBox(container)
        self.countdown_spin.setRange(0, 10)
        self.countdown_spin.setValue(int(self.settings.get("Countdown", 3)))
        self.countdown_spin.setSuffix(" 秒")
        options.addRow("开始倒计时", self.countdown_spin)

        self.repeat_spin = QSpinBox(container)
        self.repeat_spin.setRange(30, 1000)
        self.repeat_spin.setValue(int(self.settings.get("Repeat Interval", 110)))
        self.repeat_spin.setSuffix(" 毫秒")
        options.addRow("普攻连点间隔", self.repeat_spin)

        self.sequence_mode_check = QCheckBox(
            "推进模式：按顺序执行并确认切人，不按绝对时间戳；适合时间戳不准的轴和文字轴", container
        )
        self.sequence_mode_check.setChecked(bool(self.settings.get("Sequence Mode", True)))
        options.addRow("播放模式", self.sequence_mode_check)

        self.basic_interval_spin = QSpinBox(container)
        self.basic_interval_spin.setRange(100, 2000)
        self.basic_interval_spin.setValue(int(self.settings.get("Basic Interval", 450)))
        self.basic_interval_spin.setSuffix(" 毫秒")
        options.addRow("普攻出手间隔（推进模式）", self.basic_interval_spin)

        self.loop_check = QCheckBox(
            "从循环起点循环播放直到战斗结束；建议同时开启目标丢失暂停以自动判定结束", container
        )
        self.loop_check.setChecked(bool(self.settings.get("Loop Playback", False)))
        options.addRow("循环播放（推进模式）", self.loop_check)

        self.loop_start_spin = QSpinBox(container)
        self.loop_start_spin.setRange(1, 5000)
        self.loop_start_spin.setValue(int(self.settings.get("Loop Start", 1)))
        self.loop_start_spin.setPrefix("第 ")
        self.loop_start_spin.setSuffix(" 步")
        options.addRow("循环起点（时间轴预览行号）", self.loop_start_spin)

        self.start_trigger_check = QCheckBox("播放开始时自动触发轴内的“开始”按键", container)
        self.start_trigger_check.setChecked(bool(self.settings.get("Start Trigger", True)))
        options.addRow("挑战触发", self.start_trigger_check)

        self.visual_sync_check = QCheckBox(
            "切人校验：推进模式立刻衔接下一动作、后台确认失败自动补按一次；时间轴模式同步等待", container
        )
        self.visual_sync_check.setChecked(bool(self.settings.get("Visual Sync", True)))
        options.addRow("视觉同步", self.visual_sync_check)

        self.sync_timeout_spin = QDoubleSpinBox(container)
        self.sync_timeout_spin.setRange(0.2, 3.0)
        self.sync_timeout_spin.setSingleStep(0.1)
        self.sync_timeout_spin.setValue(float(self.settings.get("Sync Timeout", 1.5)))
        self.sync_timeout_spin.setSuffix(" 秒")
        options.addRow("同步超时", self.sync_timeout_spin)

        self.target_pause_check = QCheckBox(
            "boss 击杀/转火出现空档时暂停时间轴，重新锁定目标后继续", container
        )
        self.target_pause_check.setChecked(bool(self.settings.get("Target Pause", False)))
        options.addRow("目标丢失暂停", self.target_pause_check)

        self.target_wait_spin = QSpinBox(container)
        self.target_wait_spin.setRange(5, 120)
        self.target_wait_spin.setValue(int(self.settings.get("Target Wait", 30)))
        self.target_wait_spin.setSuffix(" 秒")
        options.addRow("新目标等待上限", self.target_wait_spin)

        self.target_timeout_stop_check = QCheckBox(
            "等待超时后停止播放；不勾选则超时后继续按时间轴执行", container
        )
        self.target_timeout_stop_check.setChecked(bool(self.settings.get("Target Timeout Stop", False)))
        options.addRow("超时行为", self.target_timeout_stop_check)

        self.auto_combat_pause_check = QCheckBox(
            "椰果结束后暂停自动战斗；不勾选则结束后由自动战斗接管战斗", container
        )
        self.auto_combat_pause_check.setChecked(bool(self.settings.get("Pause Auto Combat After", False)))
        options.addRow("自动战斗交接", self.auto_combat_pause_check)

        # 触发页已移除，自动战斗（角色逻辑）在这里开关。
        self.auto_combat_enable_check = QCheckBox(
            "启用自动战斗（角色逻辑；爱达千等角色轴写在“角色代码”页）", container
        )
        self.auto_combat_enable_check.stateChanged.connect(self._toggle_auto_combat)
        options.addRow("自动战斗", self.auto_combat_enable_check)
        QTimer.singleShot(800, self._sync_auto_combat_enabled)
        layout.addLayout(options)

        layout.addWidget(
            BodyLabel(
                "输入归属：播放期间由椰果启动器独占游戏输入；自动战斗开启时，启动前与结束后由自动战斗操作角色，交接会显示在下方状态栏。"
            )
        )

        self.current_input_label = QLabel("当前按键：无", container)
        self.current_action_label = QLabel("程序输出：等待", container)
        self.timing_label = QLabel("时间偏差：等待", container)
        self.status_label = BodyLabel("导入轴后即可执行；F10 可随时紧急停止。")
        layout.addWidget(self.current_input_label)
        layout.addWidget(self.current_action_label)
        layout.addWidget(self.timing_label)
        layout.addWidget(self.status_label)

        self.progress = QProgressBar(container)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.stop_button = PushButton("停止并释放按键", container)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_playback)
        self.play_button = PrimaryPushButton("启动椰果", container)
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self._start_playback)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.play_button)
        layout.addLayout(buttons)
        self.add_card("执行控制", container)

    def _find_auto_combat_task(self):
        executor = getattr(self, "executor", None)
        for task in getattr(executor, "trigger_tasks", ()) or ():
            if type(task).__name__ == "AutoCombatTask":
                return task
        return None

    def _sync_auto_combat_enabled(self):
        task = self._find_auto_combat_task()
        if task is None:
            # 执行器尚未就绪，稍后重试。
            QTimer.singleShot(1000, self._sync_auto_combat_enabled)
            return
        self.auto_combat_enable_check.blockSignals(True)
        self.auto_combat_enable_check.setChecked(bool(task.enabled))
        self.auto_combat_enable_check.blockSignals(False)

    def _toggle_auto_combat(self):
        task = self._find_auto_combat_task()
        if task is None:
            return
        if self.auto_combat_enable_check.isChecked():
            task.enable()
        else:
            task.disable()

    def _connect_playback_task(self):
        if self.playback_task is None and self.executor is not None:
            self.playback_task = self.get_task(AxisPlaybackTask)
        if self.playback_task is None or self.task_signals_connected:
            return self.playback_task
        signals = self.playback_task.signals
        signals.status_changed.connect(self.status_label.setText)
        signals.action_changed.connect(self._action_changed)
        signals.progress_changed.connect(self.progress.setValue)
        signals.timing_changed.connect(self._timing_changed)
        signals.playback_finished.connect(self._playback_finished)
        self.task_signals_connected = True
        return self.playback_task

    def _import_local(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择椰果启动器轴",
            "",
            "WWCOMBO 椰果启动器轴 (*.wwcombo.json *.json)",
        )
        if not path:
            return
        try:
            self._load_chart(load_axis_file(path), path)
        except AxisFormatError as error:
            self._show_error(str(error))

    def _import_community(self) -> None:
        identifier = self.community_input.text().strip()
        if not identifier:
            self._show_error("请先粘贴社区轴 ID 或链接")
            return
        self.settings["Community Axis"] = identifier
        self.community_button.setEnabled(False)
        self.status_label.setText("正在下载并校验社区轴……")

        def worker():
            try:
                chart = download_community_chart(identifier)
                self.import_signals.imported.emit(chart, identifier)
            except Exception as error:
                self.import_signals.failed.emit(str(error))

        threading.Thread(target=worker, name="AxisCommunityImport", daemon=True).start()

    def _community_imported(self, chart: AxisChart, source: str) -> None:
        self.community_button.setEnabled(True)
        self._load_chart(chart, source)

    def _community_failed(self, message: str) -> None:
        self.community_button.setEnabled(True)
        self.status_label.setText("社区轴导入失败")
        self._show_error(message)

    def _load_chart(self, chart: AxisChart, source: str) -> None:
        self.chart = chart
        minutes, seconds = divmod(chart.duration_ms / 1000, 60)
        self.chart_summary.setText(
            f"{chart.title}｜{len(chart.steps)} 个动作｜{int(minutes):02d}:{seconds:05.2f}｜wwcombo v{chart.version}"
        )
        self.status_label.setText(f"已导入：{source}")
        self.progress.setValue(0)
        self.timing_label.setText("时间偏差：等待")
        self._fill_mapping_table()
        self._fill_timeline_table()
        self.play_button.setEnabled(True)

    def _fill_mapping_table(self) -> None:
        task = self._connect_playback_task()
        hotkeys = getattr(task, "key_config", {}) if task else {}
        defaults = build_default_output_mapping(self.chart, hotkeys)
        saved = self.settings.get("Move Mappings", {}).get(self._chart_settings_key(), {})
        self.mapping_table.setRowCount(len(self.chart.move_ids))
        for row, move_id in enumerate(self.chart.move_ids):
            label_item = QTableWidgetItem(self.chart.label_for(move_id))
            label_item.setData(Qt.UserRole, move_id)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            author_codes = " / ".join(self.chart.binding_codes.get(move_id, ())) or "未提供"
            author_item = QTableWidgetItem(author_codes)
            author_item.setFlags(author_item.flags() & ~Qt.ItemIsEditable)

            binding = defaults.get(move_id)
            if move_id in saved:
                try:
                    binding = parse_output_binding(saved[move_id])
                except AxisFormatError:
                    pass
            output_item = QTableWidgetItem(binding.config_text if binding else "")
            if binding is None:
                if self.chart.is_noop_move(move_id):
                    output_item.setToolTip("空招式仅占用时间线位置，无需实际输出")
                else:
                    output_item.setToolTip("这个动作无法自动识别，请手动填写实际输出")
            self.mapping_table.setItem(row, 0, label_item)
            self.mapping_table.setItem(row, 1, author_item)
            self.mapping_table.setItem(row, 2, output_item)

    def _fill_timeline_table(self) -> None:
        self.timeline_table.setRowCount(len(self.chart.steps))
        for row, step in enumerate(self.chart.steps):
            values = [
                f"{step.start_ms / 1000:.3f} s",
                str(step.character_slot or "-"),
                step.label,
                f"{step.duration_ms / 1000:.3f} s",
                step.lane,
            ]
            for column, value in enumerate(values):
                self.timeline_table.setItem(row, column, QTableWidgetItem(value))

    def _collect_mappings(self):
        mappings = {}
        saved = {}
        for row in range(self.mapping_table.rowCount()):
            move_id = self.mapping_table.item(row, 0).data(Qt.UserRole)
            label = self.mapping_table.item(row, 0).text()
            text = self.mapping_table.item(row, 2).text().strip()
            if not text:
                if self.chart.is_noop_move(move_id):
                    mappings[move_id] = None
                    continue
                raise AxisFormatError(f"动作“{label}”尚未配置实际输出")
            try:
                binding = parse_output_binding(text)
            except AxisFormatError as error:
                raise AxisFormatError(f"动作“{label}”：{error}") from error
            mappings[move_id] = binding
            saved[move_id] = binding.config_text
        all_saved = dict(self.settings.get("Move Mappings", {}))
        all_saved[self._chart_settings_key()] = saved
        self.settings["Move Mappings"] = all_saved
        return mappings

    def _chart_settings_key(self) -> str:
        return self.chart.chart_id or self.chart.title

    def _start_playback(self) -> None:
        task = self._connect_playback_task()
        if task is None:
            self._show_error("找不到椰果启动器任务，请重启 椰果启动器")
            return
        if self.chart is None:
            self._show_error("请先导入椰果启动器轴")
            return
        try:
            mappings = self._collect_mappings()
            self._save_playback_options()
            task.configure_playback(
                self.chart,
                mappings,
                self.speed_spin.value(),
                self.countdown_spin.value(),
                self.repeat_spin.value(),
                self.start_trigger_check.isChecked(),
                self.visual_sync_check.isChecked(),
                self.sync_timeout_spin.value(),
                self.target_pause_check.isChecked(),
                self.target_wait_spin.value(),
                self.target_timeout_stop_check.isChecked(),
                self.auto_combat_pause_check.isChecked(),
                self.sequence_mode_check.isChecked(),
                self.basic_interval_spin.value(),
                self.loop_check.isChecked(),
                self.loop_start_spin.value(),
            )
            task.start()
        except Exception as error:
            self._show_error(str(error))
            return
        self.progress.setValue(0)
        self.timing_label.setText("时间偏差：等待")
        self.play_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("已加入任务队列")

    def _stop_playback(self) -> None:
        task = self._connect_playback_task()
        if task is not None:
            task.request_stop()
        self.status_label.setText("正在停止并释放按键……")

    def _emergency_stop(self) -> None:
        task = self._connect_playback_task()
        if task is not None and (task.running or task.enabled):
            self._stop_playback()

    def _action_changed(self, step_index: int, label: str, binding: str) -> None:
        self.current_action_label.setText(f"程序输出：{label} → {binding}")
        if step_index >= 0 and step_index < self.timeline_table.rowCount():
            self.timeline_table.selectRow(step_index)

    def _timing_changed(self, current_ms: float, average_ms: float, max_ms: float) -> None:
        self.timing_label.setText(
            f"时间偏差：当前 {current_ms:+.1f} ms｜平均 {average_ms:.1f} ms｜最大 {max_ms:.1f} ms"
        )

    def _playback_finished(self, _cancelled: bool, message: str) -> None:
        self.status_label.setText(message)
        self.current_action_label.setText("程序输出：等待")
        self.play_button.setEnabled(self.chart is not None)
        self.stop_button.setEnabled(False)

    def _physical_input_changed(self, text: str) -> None:
        self.current_input_label.setText(f"当前按键：{text or '无'}")

    def _monitor_error(self, message: str) -> None:
        self.current_input_label.setText("当前按键：监听不可用")
        self.status_label.setText(message)

    def _save_playback_options(self) -> None:
        self.settings["Speed"] = self.speed_spin.value()
        self.settings["Countdown"] = self.countdown_spin.value()
        self.settings["Repeat Interval"] = self.repeat_spin.value()
        self.settings["Start Trigger"] = self.start_trigger_check.isChecked()
        self.settings["Visual Sync"] = self.visual_sync_check.isChecked()
        self.settings["Sync Timeout"] = self.sync_timeout_spin.value()
        self.settings["Target Pause"] = self.target_pause_check.isChecked()
        self.settings["Target Wait"] = self.target_wait_spin.value()
        self.settings["Target Timeout Stop"] = self.target_timeout_stop_check.isChecked()
        self.settings["Pause Auto Combat After"] = self.auto_combat_pause_check.isChecked()
        self.settings["Sequence Mode"] = self.sequence_mode_check.isChecked()
        self.settings["Basic Interval"] = self.basic_interval_spin.value()
        self.settings["Loop Playback"] = self.loop_check.isChecked()
        self.settings["Loop Start"] = self.loop_start_spin.value()

    def _show_error(self, message: str) -> None:
        show_info_bar(self.window(), message, title="错误", error=True)

    def closeEvent(self, event):
        self.input_monitor.stop()
        super().closeEvent(event)
