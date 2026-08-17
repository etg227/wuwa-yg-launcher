"""爱达千内置轴（爱弥斯1 / 达妮娅2 / 千咲3）。

用 okww 的角色逻辑实现，不是宏回放：技能释放走 BaseChar 的确认型方法
（click_resonance / click_liberation / click_echo），大招放不出来时按原
脚本的方式平 A 补能量等待，而不是固定睡眠；切人走 get_switch_priority
+ switch_next_char 的框架原生机制（学 Zani/Phoebe 等角色的团队协同写
法），不是绕过框架直接发按键。

轴数据来自用户提供的鼠标宏截图，逐键转录为 (按键, 按住毫秒, 等待毫秒)
序列；解析时按切人键切段，每段执行者固定，段内动作用角色自身方法打出。
爱弥斯先手在场按下 R 开打；启动轴打完自动进入循环轴，直到战斗结束。
"""

import time

from src.char.BaseChar import SwitchPriority

AXIS_TEAM = ("Aemeath", "Denia", "Chisa")
SLOT_OWNER = {"1": "Aemeath", "2": "Denia", "3": "Chisa"}

# 宏原始按键序列：(按键, 按住毫秒, 松开后等待毫秒)。
# 'a'=鼠标左键，'space'=跳跃，'1'/'2'/'3'=切人。
OPENER = (
    ("3", 50, 50),
    ("space", 50, 100),
    ("a", 50, 500),
    ("e", 50, 200),
    ("a", 50, 100),
    ("1", 78, 450),
    ("a", 78, 450),
    ("2", 50, 100),
    ("e", 50, 50),
    ("r", 50, 4500),
    ("a", 50, 0),
    ("3", 50, 100),
    ("a", 50, 50),
    ("1", 50, 100),
    ("a", 50, 750),
    ("e", 50, 50),
    ("3", 50, 100),
    ("a", 50, 0),
    ("2", 50, 100),
    ("a", 50, 700),
    ("a", 50, 450),
    ("1", 50, 100),
    ("a", 50, 550),
    ("a", 50, 350),
    ("e", 50, 0),
    ("2", 50, 100),
    ("a", 50, 0),
    ("3", 50, 100),
    ("q", 50, 0),
    ("r", 50, 3675),
    ("e", 80, 0),
    ("1", 50, 150),
    ("e", 100, 3050),
    ("3", 50, 100),
    ("a", 2200, 0),
    ("2", 50, 100),
    ("e", 50, 0),
    ("1", 50, 100),
    ("a", 50, 550),
    ("a", 50, 200),
    ("e", 50, 0),
    ("2", 50, 100),
    ("a", 50, 0),
    ("3", 50, 150),
    ("a", 50, 1150),
    ("1", 50, 1250),
    ("a", 78, 725),
    ("a", 50, 0),
    ("e", 30, 0),
    ("2", 50, 250),
    ("a", 50, 250),
    ("a", 50, 450),
    ("q", 30, 0),
    ("r", 50, 2800),
    ("1", 50, 150),
)

# 循环轴 = 启动轴删掉第2键(跳跃)和第3键(左键)，首键(3)抬起延迟改为 850。
LOOP = (("3", 50, 850),) + OPENER[3:]


def parse_segments(seq, start_owner="Aemeath"):
    """按切人键把按键序列切成 (执行者, 动作列表) 段；切人本身不计入段内动作。"""
    segments = []
    owner = start_owner
    current = []
    for key, hold, wait in seq:
        if key in SLOT_OWNER:
            if current:
                segments.append((owner, tuple(current)))
            current = []
            owner = SLOT_OWNER[key]
        else:
            current.append((key, hold, wait))
    if current:
        segments.append((owner, tuple(current)))
    return tuple(segments)


OPENER_SEGMENTS = parse_segments(OPENER)
LOOP_SEGMENTS = parse_segments(LOOP)

# 椰果启动器页展示的内置轴登记表。
BUILTIN_AXES = (
    {
        "name": "爱达千轴",
        "team": "爱弥斯(1) / 达妮娅(2) / 千咲(3)",
        "first": "爱弥斯先手在场开打",
        "description": "启动轴打完自动进入循环轴，直到战斗结束；上阵该队伍并开启自动战斗即生效，无需额外操作。",
    },
)


class AidaqianAxis:
    """爱达千队伍协同 mixin：与 BaseChar 子类多重继承使用。"""

    def in_aidaqian_team(self):
        task = self.task
        if task is None or not hasattr(task, "has_char"):
            return False
        from src.char.Aemeath import Aemeath
        from src.char.Chisa import Chisa
        from src.char.Denia import Denia
        return bool(task.has_char(Aemeath) and task.has_char(Denia) and task.has_char(Chisa))

    def axis_state(self):
        if not self.in_aidaqian_team():
            return None
        task = self.task
        combat_start = getattr(task, "combat_start", 0) or 0
        state = getattr(task, "_aidaqian_axis", None)
        if not isinstance(state, dict) or state.get("combat_start") != combat_start:
            state = {"combat_start": combat_start, "phase": "opener", "idx": 0}
            task._aidaqian_axis = state
        return state

    def axis_segments(self, state):
        return OPENER_SEGMENTS if state["phase"] == "opener" else LOOP_SEGMENTS

    def axis_advance(self, state):
        state["idx"] += 1
        if state["idx"] >= len(self.axis_segments(state)):
            state["phase"] = "loop"
            state["idx"] = 0

    def do_perform(self):
        state = self.axis_state()
        if state is None:
            return super().do_perform()
        owner, actions = self.axis_segments(state)[state["idx"]]
        if owner != type(self).__name__:
            # 上场的不是该出手的角色（被打断/切人失败后重进）：让位。
            return self.switch_next_char()
        self.axis_do(actions)
        self.axis_advance(state)
        self.switch_next_char()

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        state = self.axis_state()
        if state is not None:
            owner, _ = self.axis_segments(state)[state["idx"]]
            return SwitchPriority.MUST if owner == type(self).__name__ else SwitchPriority.NO
        return super().get_switch_priority(current_char, has_intro, target_low_con)

    def axis_do(self, actions):
        for key, hold, wait in actions:
            if key == "a":
                if hold >= 700:
                    self.heavy_attack(hold / 1000)
                else:
                    self.click()
            elif key == "space":
                self.task.send_key("space")
            elif key == "q":
                self.click_echo(time_out=0)
            elif key == "e":
                self.axis_resonance(hold)
            elif key == "r":
                self.axis_liberation()
            if wait:
                self.sleep(wait / 1000, False)

    def axis_resonance(self, hold_ms):
        # 短按用确认型释放；长按（达妮娅二段大前的强化 E 等）需要精确按住
        # 时长，click_resonance 不支持自定义按住时间，退化为原始按住。
        if hold_ms < 100:
            if self.click_resonance(time_out=1.2)[0]:
                return
        self.task.send_key(self.get_resonance_key(), down_time=hold_ms / 1000)

    def axis_liberation(self):
        # 学原脚本：大招放不出来（能量差一点/技能动画挡住识别）时平 A
        # 补能量边等边试，而不是固定睡眠等待演出。放出后由
        # click_liberation 的画面检测判定演出结束，不再固定等待毫秒数。
        if self.click_liberation(wait_if_cd_ready=0):
            return
        end = time.time() + 3.0
        while time.time() < end:
            self.click()
            self.task.next_frame()
            if self.click_liberation(wait_if_cd_ready=0):
                return

    def switch_other_char(self, allow_auto_combat=False):
        # 框架开战前/战斗后会切治疗（千咲是治疗定位），会破坏爱弥斯先手；
        # 爱达千队下改为一律停在爱弥斯，随时可以起轴。
        if self.axis_state() is None:
            return super().switch_other_char(allow_auto_combat)
        from src.char.Aemeath import Aemeath
        target = self.task.has_char(Aemeath)
        if target is None:
            return
        start = time.time()
        while time.time() - start < 6:
            in_team, current_index, _ = self.task.in_team()
            if in_team and current_index == target.index:
                for char in self.task.chars:
                    if char:
                        char.is_current_char = (char.index == current_index)
                return
            self.task.send_key(target.index + 1)
            self.sleep(0.2, False)
