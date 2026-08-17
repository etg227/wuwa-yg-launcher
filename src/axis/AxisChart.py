import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_AXIS_BYTES = 5 * 1024 * 1024
MAX_AXIS_STEPS = 5000
MAX_AXIS_DURATION_MS = 30 * 60 * 1000
COMMUNITY_BASE_URL = "https://nova.fb520.site"
COMMUNITY_ID_PATTERN = re.compile(r"wwc_[A-Za-z0-9-]{8,}")
VALID_NAMED_KEYS = {
    "esc", "tab", "shift", "lshift", "rshift", "ctrl", "lctrl", "rctrl",
    "alt", "lalt", "ralt", "enter", "return", "space", "backspace",
    "up", "down", "left", "right", "pageup", "pagedown", "home", "end",
    "insert", "delete", "capslock", "numlock", "scrolllock", "printscreen",
    "windows", "win", "command", "cmd", "meta",
}


class AxisFormatError(ValueError):
    """轴文件格式错误。"""


@dataclass(frozen=True)
class AxisStep:
    """一个已经换算为毫秒时间线的动作。"""

    step_id: str
    move_id: str
    label: str
    start_ms: float
    duration_ms: float
    character_slot: int | None = None
    lane: str = "main"


@dataclass(frozen=True)
class OutputBinding:
    """椰果启动器 实际输出的键盘或鼠标动作。"""

    kind: str
    code: str
    mode: str = "tap"

    def __post_init__(self):
        if self.kind not in {"key", "mouse"}:
            raise ValueError(f"不支持的输入类型：{self.kind}")
        if self.mode not in {"tap", "hold", "repeat"}:
            raise ValueError(f"不支持的输入模式：{self.mode}")

    @property
    def config_text(self) -> str:
        if self.kind == "mouse":
            return f"mouse:{self.code}:{self.mode}"
        if self.mode == "tap":
            return self.code
        return f"{self.code}:{self.mode}"

    @property
    def display_text(self) -> str:
        mode_text = {"tap": "轻触", "hold": "长按", "repeat": "连点"}[self.mode]
        if self.kind == "mouse":
            button_text = {"left": "鼠标左键", "right": "鼠标右键", "middle": "鼠标中键"}.get(
                self.code, self.code
            )
            return f"{button_text}（{mode_text}）"
        return f"{self.code.upper()}（{mode_text}）"


@dataclass(frozen=True)
class AxisChart:
    """解析后的 WWCOMBO 椰果启动器轴。"""

    chart_id: str
    title: str
    version: int
    steps: tuple[AxisStep, ...]
    move_labels: dict[str, str]
    binding_codes: dict[str, tuple[str, ...]]
    start_trigger_move_id: str | None = None
    stop_trigger_move_id: str | None = None

    @property
    def duration_ms(self) -> float:
        return max((step.start_ms + step.duration_ms for step in self.steps), default=0.0)

    @property
    def move_ids(self) -> tuple[str, ...]:
        result = []
        if self.start_trigger_move_id:
            result.append(self.start_trigger_move_id)
        for step in self.steps:
            if step.move_id not in result:
                result.append(step.move_id)
        return tuple(result)

    def label_for(self, move_id: str) -> str:
        return self.move_labels.get(move_id, move_id)

    def is_noop_move(self, move_id: str) -> bool:
        """空招式只占用时间线位置，不需要产生键鼠输出。"""

        compact_id = re.sub(r"[\s_-]", "", move_id).casefold()
        labels = {self.label_for(move_id)}
        labels.update(step.label for step in self.steps if step.move_id == move_id)
        compact_labels = {re.sub(r"[\s_-]", "", label).casefold() for label in labels}
        return compact_id in {"noop", "emptymove", "emptyaction"} or bool(compact_labels & {
            "空招式",
            "空动作",
            "无动作",
            "占位动作",
        })

    @classmethod
    def from_json(cls, content: str | bytes) -> "AxisChart":
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise AxisFormatError(f"无法解析 JSON：{error}") from error
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AxisChart":
        if not isinstance(payload, dict) or payload.get("type") != "wwcombo-chart":
            raise AxisFormatError("这不是 WWCOMBO 椰果启动器轴文件")

        version = _safe_int(payload.get("version"), "version")
        if version < 1 or version > 3:
            raise AxisFormatError(f"暂不支持 wwcombo 版本 {version}")

        chart = payload.get("chart")
        if not isinstance(chart, dict):
            raise AxisFormatError("缺少 chart 数据")

        raw_steps = chart.get("steps")
        if not isinstance(raw_steps, list):
            raise AxisFormatError("缺少 steps 动作列表")
        if len(raw_steps) > MAX_AXIS_STEPS:
            raise AxisFormatError(f"动作数量超过上限 {MAX_AXIS_STEPS}")

        move_labels = _parse_move_labels(payload.get("moves"))
        binding_codes = _parse_binding_codes(payload.get("bindings"))
        steps = tuple(sorted((_parse_step(item, move_labels) for item in raw_steps), key=lambda item: item.start_ms))
        duration_ms = max((step.start_ms + step.duration_ms for step in steps), default=0.0)
        if duration_ms > MAX_AXIS_DURATION_MS:
            raise AxisFormatError("椰果启动器轴总时长超过 30 分钟")

        return cls(
            chart_id=str(chart.get("id") or ""),
            title=str(chart.get("title") or "未命名椰果启动器轴"),
            version=version,
            steps=steps,
            move_labels=move_labels,
            binding_codes=binding_codes,
            start_trigger_move_id=_optional_text(chart.get("startTriggerMoveId")),
            stop_trigger_move_id=_optional_text(chart.get("stopTriggerMoveId")),
        )


def load_axis_file(path: str | Path) -> AxisChart:
    file_path = Path(path)
    try:
        size = file_path.stat().st_size
    except OSError as error:
        raise AxisFormatError(f"无法读取轴文件：{error}") from error
    if size > MAX_AXIS_BYTES:
        raise AxisFormatError("轴文件超过 5 MB，已拒绝导入")
    try:
        return AxisChart.from_json(file_path.read_bytes())
    except OSError as error:
        raise AxisFormatError(f"无法读取轴文件：{error}") from error


def extract_community_id(identifier: str) -> str:
    match = COMMUNITY_ID_PATTERN.search(identifier.strip())
    if not match:
        raise AxisFormatError("请输入社区轴 ID、详情链接或下载链接")
    return match.group(0)


def download_community_chart(identifier: str) -> AxisChart:
    """只从固定社区域名下载轴，避免把用户输入当作任意网址请求。"""

    import requests

    community_id = extract_community_id(identifier)
    url = f"{COMMUNITY_BASE_URL}/api/community/download/{community_id}"
    try:
        with requests.get(
                url,
                headers={"User-Agent": "wuwa-pilot-axis-import/1.0"},
                timeout=(5, 20),
                stream=True,
                allow_redirects=False,
        ) as response:
            response.raise_for_status()
            try:
                content_length = int(response.headers.get("Content-Length") or 0)
            except ValueError as error:
                raise AxisFormatError("社区返回了无效的文件大小") from error
            if content_length > MAX_AXIS_BYTES:
                raise AxisFormatError("社区轴文件超过 5 MB，已拒绝导入")
            content = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                content.extend(chunk)
                if len(content) > MAX_AXIS_BYTES:
                    raise AxisFormatError("社区轴文件超过 5 MB，已拒绝导入")
    except AxisFormatError:
        raise
    except requests.RequestException as error:
        raise AxisFormatError(f"社区轴下载失败：{error}") from error
    return AxisChart.from_json(bytes(content))


def normalize_axis_binding(code: str) -> OutputBinding | None:
    """把浏览器 KeyboardEvent 风格代码转换为 椰果启动器 输入。"""

    raw = str(code or "").strip()
    compact = re.sub(r"[\s_-]", "", raw).casefold()
    mouse_bindings = {
        "mouseleft": OutputBinding("mouse", "left"),
        "mouselefthold": OutputBinding("mouse", "left", "hold"),
        "mouseright": OutputBinding("mouse", "right"),
        "mouserighthold": OutputBinding("mouse", "right", "hold"),
        # 社区早期客户端曾导出过这个拼写，必须继续兼容。
        "mouserighthoid": OutputBinding("mouse", "right", "hold"),
        "mousemiddle": OutputBinding("mouse", "middle"),
    }
    if compact in mouse_bindings:
        return mouse_bindings[compact]
    if compact.startswith("mouse"):
        return None

    named_keys = {
        "space": "space",
        "escape": "esc",
        "esc": "esc",
        "enter": "enter",
        "tab": "tab",
        "shiftleft": "lshift",
        "shiftright": "rshift",
        "controlleft": "lctrl",
        "controlright": "rctrl",
        "altleft": "lalt",
        "altright": "ralt",
        "arrowup": "up",
        "arrowdown": "down",
        "arrowleft": "left",
        "arrowright": "right",
    }
    if compact in named_keys:
        return OutputBinding("key", named_keys[compact])
    if compact.startswith("key") and len(compact) == 4 and compact[-1].isalnum():
        return OutputBinding("key", compact[-1])
    if compact.startswith("digit") and len(compact) == 6 and compact[-1].isdigit():
        return OutputBinding("key", compact[-1])
    if re.fullmatch(r"f(?:[1-9]|1[0-2])", compact):
        return OutputBinding("key", compact)
    if len(compact) == 1 and compact.isalnum():
        return OutputBinding("key", compact)
    return None


def parse_output_binding(text: str) -> OutputBinding:
    """解析映射表中可编辑的输出格式。"""

    raw = text.strip().casefold()
    if not raw:
        raise AxisFormatError("输出按键不能为空")

    parts = [part.strip() for part in raw.split(":")]
    if parts[0] == "mouse":
        if len(parts) not in {2, 3} or parts[1] not in {"left", "right", "middle"}:
            raise AxisFormatError(f"无法识别鼠标映射：{text}")
        mode = parts[2] if len(parts) == 3 else "tap"
        try:
            return OutputBinding("mouse", parts[1], mode)
        except ValueError as error:
            raise AxisFormatError(str(error)) from error

    mode = "tap"
    key = parts[0]
    if len(parts) == 2:
        mode = parts[1]
    elif len(parts) > 2:
        raise AxisFormatError(f"无法识别按键映射：{text}")
    valid_function_key = re.fullmatch(r"f(?:[1-9]|1[0-2])", key)
    valid_character = len(key) == 1 and (key.isalnum() or key in " `~!@#$%^&*()-_=+[{]}\\|;:'\",<.>/?")
    if key not in VALID_NAMED_KEYS and not valid_function_key and not valid_character:
        raise AxisFormatError(f"无法识别按键：{key}")
    try:
        return OutputBinding("key", key, mode)
    except ValueError as error:
        raise AxisFormatError(str(error)) from error


def build_default_output_mapping(chart: AxisChart, game_hotkeys: dict | None = None) -> dict[str, OutputBinding | None]:
    """按动作语义优先适配本机游戏热键，未知动作再采用轴作者的绑定。"""

    hotkeys = game_hotkeys or {}
    skill_key = str(hotkeys.get("Resonance Key", "e")).casefold()
    semantic_defaults = {
        "basic_attack": OutputBinding("mouse", "left", "repeat"),
        "heavy_attack": OutputBinding("mouse", "left", "hold"),
        "skill": OutputBinding("key", skill_key),
        "skill_hold": OutputBinding("key", skill_key, "hold"),
        "resonance_skill_hold": OutputBinding("key", skill_key, "hold"),
        "echo": OutputBinding("key", str(hotkeys.get("Echo Key", "q")).casefold()),
        "liberation": OutputBinding("key", str(hotkeys.get("Liberation Key", "r")).casefold()),
        "dodge": OutputBinding("key", str(hotkeys.get("Dodge Key", "lshift")).casefold()),
        "dodge_hold": OutputBinding("key", str(hotkeys.get("Dodge Key", "lshift")).casefold(), "hold"),
        "jump": OutputBinding("key", str(hotkeys.get("Jump Key", "space")).casefold()),
        "switch_1": OutputBinding("key", "1"),
        "switch_2": OutputBinding("key", "2"),
        "switch_3": OutputBinding("key", "3"),
    }
    result: dict[str, OutputBinding | None] = {}
    for move_id in chart.move_ids:
        binding = semantic_defaults.get(move_id)
        labels = {chart.label_for(move_id)}
        labels.update(step.label for step in chart.steps if step.move_id == move_id)
        compact_labels = {re.sub(r"[\s_-]", "", label).casefold() for label in labels}
        if binding is None and "长按技能" in compact_labels:
            binding = OutputBinding("key", skill_key, "hold")
        if binding is None:
            binding = next(
                (parsed for code in chart.binding_codes.get(move_id, ()) if (parsed := normalize_axis_binding(code))),
                None,
            )
        result[move_id] = binding
    return result


def _parse_step(raw_step: Any, move_labels: dict[str, str]) -> AxisStep:
    if not isinstance(raw_step, dict):
        raise AxisFormatError("steps 中包含无效动作")
    move_id = _required_text(raw_step.get("moveId"), "step.moveId")
    sample = _select_sample(raw_step.get("samples"))
    fallback_start = _range_center(raw_step.get("startMin"), raw_step.get("startMax"), "step.start")
    fallback_duration = _range_center(raw_step.get("durationMin"), raw_step.get("durationMax"), "step.duration")
    start_ms = _safe_number(sample.get("startTime", fallback_start), "sample.startTime")
    duration_ms = _safe_number(sample.get("duration", fallback_duration), "sample.duration")
    if start_ms < 0 or duration_ms < 0:
        raise AxisFormatError("动作时间不能为负数")
    label = str(raw_step.get("label") or move_labels.get(move_id) or move_id)
    character_slot = raw_step.get("characterSlot")
    if character_slot is not None:
        character_slot = _safe_int(character_slot, "step.characterSlot")
    return AxisStep(
        step_id=str(raw_step.get("id") or ""),
        move_id=move_id,
        label=label,
        start_ms=start_ms,
        duration_ms=duration_ms,
        character_slot=character_slot,
        lane=str(raw_step.get("lane") or "main"),
    )


def _select_sample(raw_samples: Any) -> dict[str, Any]:
    if not isinstance(raw_samples, list) or not raw_samples:
        return {}
    valid_samples = [sample for sample in raw_samples if isinstance(sample, dict)]
    if not valid_samples:
        return {}
    return next((sample for sample in valid_samples if sample.get("recordingId") == "initial"), valid_samples[0])


def _parse_move_labels(raw_moves: Any) -> dict[str, str]:
    if not isinstance(raw_moves, list):
        return {}
    result = {}
    for move in raw_moves:
        if isinstance(move, dict) and move.get("id"):
            move_id = str(move["id"])
            result[move_id] = str(move.get("label") or move_id)
    return result


def _parse_binding_codes(raw_bindings: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(raw_bindings, list):
        return {}
    result = {}
    for binding in raw_bindings:
        if not isinstance(binding, dict) or not binding.get("moveId"):
            continue
        inputs = binding.get("inputs")
        if not isinstance(inputs, list):
            continue
        codes = tuple(str(item.get("code")) for item in inputs if isinstance(item, dict) and item.get("code"))
        result[str(binding["moveId"])] = codes
    return result


def _range_center(minimum: Any, maximum: Any, field: str) -> float:
    if minimum is None and maximum is None:
        return 0.0
    if minimum is None:
        return _safe_number(maximum, field)
    if maximum is None:
        return _safe_number(minimum, field)
    return (_safe_number(minimum, field) + _safe_number(maximum, field)) / 2


def _safe_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise AxisFormatError(f"{field} 不是有效数字") from error
    if not math.isfinite(number):
        raise AxisFormatError(f"{field} 不是有限数字")
    return number


def _safe_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise AxisFormatError(f"{field} 不是有效整数") from error


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AxisFormatError(f"缺少 {field}")
    return text


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
