import re

from src.axis.AxisChart import AxisChart, AxisFormatError, AxisStep, MAX_AXIS_STEPS

# 文字轴语法：空白分隔的动作序列，# 到行尾是注释。
# 1/2/3=切人  a=普攻(a3=三次)  e=共鸣技能(e1.5=长按1.5秒)  q=声骸  r=共鸣解放
# d/闪=闪避  j/跳=跳跃  z/重=重击(z1.2=长按1.2秒)  f=处决或交互
# w0.5/等0.5=等待0.5秒  循环/loop=之后的步骤循环播放
ALIASES = {
    "普": "a",
    "技": "e",
    "声": "q",
    "大": "r",
    "闪": "d",
    "跳": "j",
    "重": "z",
    "切1": "1",
    "切2": "2",
    "切3": "3",
}
MOVE_DEFS = {
    "a": ("basic_attack", "普攻", 100.0),
    "e": ("skill", "共鸣技能", 900.0),
    "q": ("echo", "声骸", 500.0),
    "r": ("liberation", "共鸣解放", 2000.0),
    "d": ("dodge", "闪避", 400.0),
    "j": ("jump", "跳跃", 400.0),
    "f": ("f_key", "处决/交互", 600.0),
    "1": ("switch_1", "切人 1", 900.0),
    "2": ("switch_2", "切人 2", 900.0),
    "3": ("switch_3", "切人 3", 900.0),
}
LOOP_MARKERS = {"循环", "loop"}
TEXT_AXIS_CHART_ID = "text_axis"


def parse_text_axis(text: str) -> tuple[AxisChart, int | None]:
    """把文字轴解析成合成轴；返回轴和循环起点步序号（0 基，无循环为 None）。"""

    tokens = []
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        tokens.extend(line.split())
    if not tokens:
        raise AxisFormatError("文字轴为空，请输入动作序列")

    steps = []
    move_labels = {}
    loop_start = None
    clock_ms = 0.0

    def append_step(move_id: str, label: str, duration_ms: float, count: int = 1) -> None:
        nonlocal clock_ms
        for _ in range(count):
            if len(steps) >= MAX_AXIS_STEPS:
                raise AxisFormatError(f"文字轴步骤超过上限 {MAX_AXIS_STEPS}")
            steps.append(
                AxisStep(
                    step_id=f"text_{len(steps)}",
                    move_id=move_id,
                    label=label,
                    start_ms=clock_ms,
                    duration_ms=duration_ms,
                )
            )
            move_labels[move_id] = label
            clock_ms += max(duration_ms, 1.0)

    for position, raw in enumerate(tokens, start=1):
        token = ALIASES.get(raw, raw).casefold()
        token = ALIASES.get(token, token)
        if token in LOOP_MARKERS:
            if loop_start is not None:
                raise AxisFormatError("文字轴只能有一个循环标记")
            loop_start = len(steps)
            continue
        if match := re.fullmatch(r"a(\d{1,2})?", token):
            count = int(match.group(1) or 1)
            if count < 1:
                raise AxisFormatError(f"第 {position} 个动作“{raw}”次数无效")
            move_id, label, duration = MOVE_DEFS["a"]
            append_step(move_id, label, duration, count)
            continue
        if match := re.fullmatch(r"z(\d+(?:\.\d+)?)?", token):
            duration_ms = float(match.group(1) or 0.6) * 1000
            if duration_ms < 100 or duration_ms > 10000:
                raise AxisFormatError(f"第 {position} 个动作“{raw}”长按时长无效")
            append_step("heavy_attack", "重击", duration_ms)
            continue
        if match := re.fullmatch(r"e(\d+(?:\.\d+)?)", token):
            # 洛瑟拉、齐莎这类角色的共鸣技能需要长按；按下保持后释放。
            duration_ms = float(match.group(1)) * 1000
            if duration_ms < 100 or duration_ms > 10000:
                raise AxisFormatError(f"第 {position} 个动作“{raw}”长按时长无效")
            append_step("skill_hold", "长按共鸣技能", duration_ms)
            continue
        if match := re.fullmatch(r"(?:w|等)(\d+(?:\.\d+)?)", token):
            duration_ms = float(match.group(1)) * 1000
            if duration_ms <= 0 or duration_ms > 60000:
                raise AxisFormatError(f"第 {position} 个动作“{raw}”等待时长无效")
            append_step("noop", "等待", duration_ms)
            continue
        if token in MOVE_DEFS:
            move_id, label, duration = MOVE_DEFS[token]
            append_step(move_id, label, duration)
            continue
        raise AxisFormatError(f"无法识别第 {position} 个动作：{raw}")

    if not steps:
        raise AxisFormatError("文字轴没有可执行的动作")
    if loop_start is not None and loop_start >= len(steps):
        raise AxisFormatError("循环标记后面必须还有动作")

    chart = AxisChart(
        chart_id=TEXT_AXIS_CHART_ID,
        title="文字轴",
        version=3,
        steps=tuple(steps),
        move_labels=move_labels,
        binding_codes={"f_key": ("KeyF",)},
    )
    return chart, loop_start
