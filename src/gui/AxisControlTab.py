from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, FluentIcon, StrongBodyLabel

from ok.gui.widget.CustomTab import CustomTab
from ok.util.config import Config
from src.char.AidaqianAxis import BUILTIN_AXES as AIDAQIAN_BUILTIN_AXES
from src.char.YangqianSuiAxis import BUILTIN_AXIS_ENTRY as YANGQIANSUI_BUILTIN_AXIS

BUILTIN_AXES = AIDAQIAN_BUILTIN_AXES + (YANGQIANSUI_BUILTIN_AXIS,)
# 与 config.py 里 char_config_option 是同一份文件（按名字对应），角色代码通过
# task.char_config 读取；这里直接读写同一份 Config，页面上勾选即时生效。
CHAR_CONFIG_DEFAULTS = {
    'Iuno C6': False,
    'Chisa DPS': False,
    'Suisui Signature Weapon': True,
}


class AxisCard(QFrame):
    """单条内置轴的信息卡片；轴本身只展示，但轴相关的角色配置开关放在这里。"""

    def __init__(self, axis, char_config, parent=None):
        super().__init__(parent)
        self.setObjectName("axisCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        layout.addWidget(StrongBodyLabel(axis["name"], self))
        layout.addWidget(BodyLabel(f"队伍：{axis['team']}", self))
        layout.addWidget(BodyLabel(f"开局：{axis['first']}", self))
        desc = CaptionLabel(axis["description"], self)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        for key in axis.get("char_config_switches", ()):
            check = QCheckBox(key["label"], self)
            check.setChecked(bool(char_config.get(key["key"], key["default"])))
            check.stateChanged.connect(
                lambda state, k=key["key"]: char_config.__setitem__(k, bool(state)))
            layout.addWidget(check)


class AxisControlTab(CustomTab):
    """椰果启动器：内置轴库展示 + 自动战斗开关。

    不支持用户导入轴或修改轴数据——轴以角色逻辑方式内置在角色代码里，
    上阵对应队伍并开启自动战斗即自动生效。想自己写轴请到“开发者模式”。
    """

    def __init__(self):
        super().__init__()
        container = QWidget(self.view)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(16)

        intro = BodyLabel(
            "椰果启动器的轴内置在角色自身的行动逻辑里，不支持导入或编辑轴文件；"
            "上阵下方队伍并开启自动战斗即自动生效。想自己写轴，请前往“开发者模式”。",
            container,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        toggle_row = QHBoxLayout()
        self.auto_combat_check = QCheckBox("启用自动战斗（角色逻辑，内置轴由此驱动）", container)
        self.auto_combat_check.stateChanged.connect(self._toggle_auto_combat)
        toggle_row.addWidget(self.auto_combat_check)
        toggle_row.addStretch(1)
        layout.addLayout(toggle_row)
        QTimer.singleShot(800, self._sync_auto_combat_enabled)

        char_config = Config('Character Config', CHAR_CONFIG_DEFAULTS)
        layout.addWidget(StrongBodyLabel("内置轴库", container))
        for axis in BUILTIN_AXES:
            layout.addWidget(AxisCard(axis, char_config, container))
        layout.addStretch(1)

        self.vBoxLayout.addWidget(container)

    @property
    def name(self):
        return "椰果启动器"

    @property
    def icon(self):
        return FluentIcon.PLAY

    # ---------- 自动战斗开关 ----------

    def _find_auto_combat_task(self):
        executor = getattr(self, "executor", None)
        for task in getattr(executor, "trigger_tasks", ()) or ():
            if type(task).__name__ == "AutoCombatTask":
                return task
        return None

    def _sync_auto_combat_enabled(self):
        task = self._find_auto_combat_task()
        if task is None:
            QTimer.singleShot(1000, self._sync_auto_combat_enabled)
            return
        self.auto_combat_check.blockSignals(True)
        self.auto_combat_check.setChecked(bool(task.enabled))
        self.auto_combat_check.blockSignals(False)

    def _toggle_auto_combat(self):
        task = self._find_auto_combat_task()
        if task is None:
            return
        if self.auto_combat_check.isChecked():
            task.enable()
        else:
            task.disable()
