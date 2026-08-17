import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QListWidgetItem, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, FluentIcon, ListWidget, MessageBox, PrimaryPushButton, PushButton

from ok import og
from ok.gui.tasks.EditTaskTab import CodeEditor
from ok.gui.tasks.PythonHighlighter import PythonHighlighter
from ok.gui.util.app import show_info_bar
from ok.gui.widget.CustomTab import CustomTab
from ok.util.config import Config

WARNING_TEXT = (
    "开发者模式允许你直接用 Python 编写轴、修改角色逻辑或做其它更改。\n\n"
    "开启前请确保你有一定的 Python 代码能力：\n"
    "· 脚本会在本程序进程内直接执行，写错可能导致程序异常甚至崩溃；\n"
    "· 出现问题时请先删除或修正 dev_scripts 目录里的脚本再重启；\n"
    "· 不要运行来路不明的脚本，它们拥有与本程序相同的权限。"
)

EXAMPLE_SCRIPT = '''"""开发者模式示例脚本。

启动时会自动执行 dev_scripts 目录下的所有 .py 文件（按文件名排序），
在右侧编辑保存后点“重载全部脚本”也会重新执行。

可用对象：
    og           ok 框架全局对象（og.executor 为任务执行器）

示例：用 Python 写轴（角色逻辑方式），可参考“角色代码”页里各角色的写法，
把自定义角色类写在这里并通过 CustomCharLoader 的机制保存，或直接修改
og.executor 里任务/角色的行为。
"""

# print 会输出到日志文件，便于确认脚本已执行。
print("dev_scripts 示例脚本已加载")
'''


def dev_scripts_dir(create=True):
    folder = Path(Config.config_folder) / "dev_scripts"
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    return folder


class DeveloperTab(CustomTab):
    def __init__(self):
        super().__init__()
        self.settings = Config("DeveloperTab", {"accepted": False})
        self.current_file = None
        self.editor = None
        self.file_list = None
        self._gate_container = None
        if self.settings.get("accepted"):
            self._build_editor()
            self._run_all_scripts(startup=True)
        else:
            self._build_gate()

    @property
    def name(self):
        return "开发者模式"

    @property
    def icon(self):
        return FluentIcon.DEVELOPER_TOOLS

    # ---------- 开启前的确认 ----------

    def _build_gate(self):
        container = QWidget(self.view)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(16)
        warn = BodyLabel(WARNING_TEXT)
        warn.setWordWrap(True)
        layout.addWidget(warn)
        row = QHBoxLayout()
        enable_button = PrimaryPushButton(FluentIcon.DEVELOPER_TOOLS, "我已了解风险，启用开发者模式")
        enable_button.clicked.connect(self._confirm_enable)
        row.addWidget(enable_button)
        row.addStretch(1)
        layout.addLayout(row)
        self._gate_container = container
        self.vBoxLayout.addWidget(container)

    def _confirm_enable(self):
        box = MessageBox(
            "启用开发者模式？",
            "请确保你有一定的 Python 代码能力。脚本在程序进程内执行，"
            "写错可能导致程序异常；问题脚本需手动删除后重启。",
            self.window(),
        )
        box.yesButton.setText("启用")
        box.cancelButton.setText("取消")
        if not box.exec():
            return
        self.settings["accepted"] = True
        if self._gate_container is not None:
            self._gate_container.setParent(None)
            self._gate_container.deleteLater()
            self._gate_container = None
        example = dev_scripts_dir() / "example.py"
        if not any(dev_scripts_dir().glob("*.py")):
            example.write_text(EXAMPLE_SCRIPT, encoding="utf-8")
        self._build_editor()

    # ---------- 编辑器 ----------

    def _build_editor(self):
        splitter = QSplitter(Qt.Horizontal, self.view)
        splitter.setChildrenCollapsible(False)

        left = QWidget(splitter)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.addWidget(BodyLabel("脚本（dev_scripts）"))
        self.file_list = ListWidget(left)
        self.file_list.currentRowChanged.connect(self._on_select_file)
        left_layout.addWidget(self.file_list, 1)
        left_buttons = QHBoxLayout()
        new_button = PushButton(FluentIcon.ADD, "新建")
        new_button.clicked.connect(self._new_file)
        delete_button = PushButton(FluentIcon.DELETE, "删除")
        delete_button.clicked.connect(self._delete_file)
        folder_button = PushButton(FluentIcon.FOLDER, "打开目录")
        folder_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(dev_scripts_dir()))))
        left_buttons.addWidget(new_button)
        left_buttons.addWidget(delete_button)
        left_buttons.addWidget(folder_button)
        left_layout.addLayout(left_buttons)

        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        hint = BodyLabel(
            "脚本在启动时自动执行，保存后点“重载全部脚本”立即生效；"
            "可用 og / og.executor，写轴建议参考“角色代码”页的角色写法。")
        hint.setWordWrap(True)
        right_layout.addWidget(hint)
        self.editor = CodeEditor(right)
        PythonHighlighter(self.editor.document())
        right_layout.addWidget(self.editor, 1)
        right_buttons = QHBoxLayout()
        save_button = PrimaryPushButton(FluentIcon.SAVE, "保存")
        save_button.clicked.connect(self._save_file)
        reload_button = PushButton(FluentIcon.SYNC, "重载全部脚本")
        reload_button.clicked.connect(self._run_all_scripts)
        right_buttons.addWidget(save_button)
        right_buttons.addWidget(reload_button)
        right_buttons.addStretch(1)
        right_layout.addLayout(right_buttons)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        self.vBoxLayout.addWidget(splitter, 1)
        self._refresh_file_list()

    def _refresh_file_list(self, select_name=None):
        self.file_list.blockSignals(True)
        self.file_list.clear()
        names = sorted(path.name for path in dev_scripts_dir().glob("*.py"))
        for name in names:
            self.file_list.addItem(QListWidgetItem(name))
        self.file_list.blockSignals(False)
        if names:
            index = names.index(select_name) if select_name in names else 0
            self.file_list.setCurrentRow(index)
        else:
            self.current_file = None
            self.editor.setPlainText("")

    def _on_select_file(self, row):
        if row < 0:
            return
        name = self.file_list.item(row).text()
        path = dev_scripts_dir() / name
        try:
            self.editor.setPlainText(path.read_text(encoding="utf-8"))
            self.current_file = path
        except OSError as error:
            show_info_bar(self.window(), f"读取失败：{error}", error=True)

    def _new_file(self):
        name, ok_clicked = QInputDialog.getText(self, "新建脚本", "文件名（.py 结尾）：")
        if not ok_clicked or not name.strip():
            return
        name = name.strip()
        if not name.endswith(".py"):
            name += ".py"
        if os.sep in name or "/" in name:
            show_info_bar(self.window(), "文件名不能包含路径", error=True)
            return
        path = dev_scripts_dir() / name
        if path.exists():
            show_info_bar(self.window(), "文件已存在", error=True)
            return
        path.write_text("# 新脚本\n", encoding="utf-8")
        self._refresh_file_list(select_name=name)

    def _delete_file(self):
        if self.current_file is None:
            return
        box = MessageBox("删除脚本？", f"将删除 {self.current_file.name}，不可恢复。", self.window())
        if not box.exec():
            return
        self.current_file.unlink(missing_ok=True)
        self.current_file = None
        self._refresh_file_list()

    def _save_file(self):
        if self.current_file is None:
            show_info_bar(self.window(), "请先选择或新建脚本", error=True)
            return
        code = self.editor.toPlainText()
        try:
            compile(code, str(self.current_file), "exec")
        except SyntaxError as error:
            show_info_bar(self.window(), f"语法错误：{error}", error=True)
            return
        self.current_file.write_text(code, encoding="utf-8")
        show_info_bar(self.window(), f"已保存 {self.current_file.name}", title="成功")

    # ---------- 执行 ----------

    def _run_all_scripts(self, startup=False):
        errors = []
        count = 0
        for path in sorted(dev_scripts_dir().glob("*.py")):
            try:
                code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
                namespace = {"og": og, "__file__": str(path), "__name__": f"dev_script_{path.stem}"}
                exec(code, namespace)  # noqa: S102 开发者模式的目的就是执行用户脚本
                count += 1
            except Exception as error:  # 单个脚本失败不影响其它脚本
                errors.append(f"{path.name}: {error}")
                self.logger.error(f"dev script failed: {path}", error)
        if startup:
            return
        if errors:
            show_info_bar(self.window(), "；".join(errors), error=True)
        else:
            show_info_bar(self.window(), f"已执行 {count} 个脚本", title="成功")
