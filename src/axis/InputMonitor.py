import threading

from PySide6.QtCore import QObject, Signal


class InputMonitor(QObject):
    """监听玩家当前按住的键，并提供独立于页面按钮的紧急停止键。"""

    held_changed = Signal(str)
    emergency_stop = Signal()
    monitor_error = Signal(str)

    def __init__(self, emergency_key: str = "F10"):
        super().__init__()
        self.emergency_key = emergency_key.upper()
        self._held = set()
        self._lock = threading.Lock()
        self._keyboard_listener = None
        self._mouse_listener = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        try:
            from pynput import keyboard, mouse

            self._keyboard_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
            self._mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
            self._keyboard_listener.start()
            self._mouse_listener.start()
            self._running = True
        except Exception as error:
            self.monitor_error.emit(f"实时按键监听启动失败：{error}")

    def stop(self) -> None:
        for listener in (self._keyboard_listener, self._mouse_listener):
            if listener is not None:
                listener.stop()
        self._keyboard_listener = None
        self._mouse_listener = None
        self._running = False
        with self._lock:
            self._held.clear()
        self.held_changed.emit("")

    def _on_key_press(self, key) -> None:
        name = self._keyboard_name(key)
        if name == self.emergency_key:
            self.emergency_stop.emit()
        self._set_held(name, True)

    def _on_key_release(self, key) -> None:
        self._set_held(self._keyboard_name(key), False)

    def _on_mouse_click(self, _x, _y, button, pressed) -> None:
        name = {
            "left": "鼠标左键",
            "right": "鼠标右键",
            "middle": "鼠标中键",
            "x1": "鼠标侧键 1",
            "x2": "鼠标侧键 2",
        }.get(getattr(button, "name", ""), str(button))
        self._set_held(name, pressed)

    def _set_held(self, name: str, pressed: bool) -> None:
        if not name:
            return
        with self._lock:
            if pressed:
                self._held.add(name)
            else:
                self._held.discard(name)
            text = " + ".join(sorted(self._held))
        self.held_changed.emit(text)

    @staticmethod
    def _keyboard_name(key) -> str:
        char = getattr(key, "char", None)
        if char:
            return str(char).upper()
        name = getattr(key, "name", None)
        if name:
            return str(name).replace("_", " ").upper()
        text = str(key).replace("Key.", "")
        return text.upper()
