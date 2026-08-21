import time

"""秧千穗 25s 双羽内置轴（秧秧 / 千咲 / 穗穗）。

这支轴不能只靠“轮到谁上场”来复现。原图里大量使用拆普攻段、快速换人、
变奏后立刻接技能等操作，因此这里把启动轴与循环轴都记录成“角色 + 明确动作”
节点。角色命中这支队伍时直接执行当前节点；不再让通用 do_perform 自己决定
这一轮要打什么。

动作记号沿用攻略图：
- a：一次普攻输入；a123 / a234 等在节点里展开成多次 a
- E：共鸣技能；Q：声骸；R：共鸣解放；Z：重击；F：F 键
- W：短按向前；下落a：空中普攻，攻击触发后立即切人保留该攻击
- 变：该节点预期由变奏入场；只做入场同步，不主动伪造协奏/变奏

轴内遵循一个统一的换人取消规则：连段内部的 A 需要等待下一段输入窗口，但只要
A 是当前角色节点的最后一个动作，A 发出并进入起手后就立即切人，不等待攻击动画
完成。A 结尾节点使用专用 fast-swap，只发目标角色切换键，不让普通战斗切人流程
自动补 A 干扰这类极限衔接。
"""

AXIS_TEAM = ("YangYangSp", "Chisa", "Suisui")

# step = (角色类名, 图中标签, 动作元组)
OPENER_STEPS = (
    ("YangYangSp", "E", ("e",)),
    ("Suisui", "a234E下落a", ("suisui_a234", "e", "fall_a")),
    ("Chisa", "aEa3", ("a", "e", "a")),
    ("Suisui", "a123", ("a", "a", "a")),
    ("Chisa", "a4", ("a",)),
    ("YangYangSp", "aE", ("a", "e")),
    ("Suisui", "a4QR", ("a", "q", "r")),
    ("Chisa", "变QRE", ("intro", "q", "r", "e")),
    ("YangYangSp", "a123", ("a", "a", "a")),
    ("Chisa", "Z", ("z",)),
    ("YangYangSp", "a12Q", ("a", "a", "q")),
    ("Chisa", "a", ("a",)),
    ("YangYangSp", "变EZREFW EZ", ("intro", "e", "z", "r", "e", "f", "w", "e", "z")),
)

LOOP_STEPS = (
    ("Suisui", "变下落a", ("intro", "fall_a")),
    ("Chisa", "aEa3", ("a", "e", "a")),
    ("Suisui", "a123", ("a", "a", "a")),
    ("Chisa", "a4", ("a",)),
    ("YangYangSp", "aE", ("a", "e")),
    # 攻略图这一格标注条件多打 E；沿用现有配置：穗穗无专武时补 E。
    ("Suisui", "a4(E条件)QR", ("a", "e_if_no_signature", "q", "r")),
    ("Chisa", "变QRE", ("intro", "q", "r", "e")),
    ("YangYangSp", "a123", ("a", "a", "a")),
    ("Chisa", "Z", ("z",)),
    ("YangYangSp", "a12Q", ("a", "a", "q")),
    ("Chisa", "a", ("a",)),
    ("YangYangSp", "变EZREFW EZ", ("intro", "e", "z", "r", "e", "f", "w", "e", "z")),
)

# 兼容可能还在引用旧常量的代码。
OPENER_ORDER = tuple(step[0] for step in OPENER_STEPS)
LOOP_ORDER = tuple(step[0] for step in LOOP_STEPS)

BUILTIN_AXIS_ENTRY = {
    "name": "秧千穗轴",
    "team": "秧秧 / 千咲 / 穗穗",
    "first": "秧秧先手；启动轴结束后自动进入循环轴，直到战斗结束",
    "description": "按‘秧千穗25s双羽轴’逐节点执行明确动作，不再只协同出场顺序；"
                   "上阵该队伍并开启自动战斗即生效。",
    "char_config_switches": (
        {"key": "Suisui Signature Weapon", "default": True, "label": "穗穗（Suisui）拥有专武"},
    ),
}


class YangqianSuiAxis:
    """秧千穗动作轴 mixin：与三个角色的 BaseChar 子类多重继承使用。"""

    # 普通连段与穗穗开局 a234 的临时时序；后续可用实测宏时间戳继续压缩。
    AXIS_BASIC_GAP = 0.28
    AXIS_SUISUI_BASIC_GAP = 0.42
    AXIS_SUISUI_A2_TO_A3_GAP = 0.75
    AXIS_SUISUI_A3_TO_A4_GAP = 0.75
    AXIS_SUISUI_A4_TO_E_GAP = 0.60

    # “A 已经起手 -> 立即换人”的窗口。不是等待攻击结束。
    AXIS_ATTACK_SWAP_GAP = 0.08
    AXIS_FALL_TRIGGER_GAP = 0.12

    # 穗穗 E 已经把角色带到空中后，还需要等技能进入可接下落 A 的窗口。
    AXIS_SUISUI_AIRBORNE_TO_FALL_GAP = 0.22

    # 千咲接穗穗下落 A 快切后的专用衔接。
    AXIS_CHISA_SWITCH_TO_FALL_GAP = 0.05
    AXIS_CHISA_FALL_TO_E_GAP = 0.28
    AXIS_CHISA_E_TO_A3_GAP = 0.32
    AXIS_CHISA_A3_SWAP_GAP = 0.10

    AXIS_SKILL_GAP = 0.16
    AXIS_ECHO_GAP = 0.12
    AXIS_F_GAP = 0.08
    AXIS_ACTION_END_GAP = 0.18
    AXIS_HEAVY_DURATION = 0.60
    AXIS_FORWARD_DURATION = 0.18
    AXIS_INTRO_TIMEOUT = 1.35
    AXIS_AIRBORNE_TIMEOUT = 0.90
    AXIS_AIRBORNE_POLL = 0.03

    # fast-swap 不补 A，只重试角色切换键并确认当前槽位。
    AXIS_FAST_SWITCH_TIMEOUT = 1.20
    AXIS_FAST_SWITCH_RETRY = 0.08

    def in_yangqiansui_team(self):
        task = self.task
        if task is None or not hasattr(task, "has_char"):
            return False
        from src.char.Chisa import Chisa
        from src.char.Suisui import Suisui
        from src.char.YangYangSp import YangYangSp
        return bool(task.has_char(YangYangSp) and task.has_char(Chisa) and task.has_char(Suisui))

    def yangqiansui_state(self):
        if not self.in_yangqiansui_team():
            return None
        task = self.task
        combat_start = getattr(task, "combat_start", 0) or 0
        state = getattr(task, "_yangqiansui_axis", None)
        if not isinstance(state, dict) or state.get("combat_start") != combat_start:
            state = {"combat_start": combat_start, "phase": "opener", "idx": 0}
            task._yangqiansui_axis = state
        return state

    def yangqiansui_steps(self, state):
        return OPENER_STEPS if state["phase"] == "opener" else LOOP_STEPS

    def yangqiansui_order(self, state):
        # 保留旧调用接口；新逻辑真正使用的是 yangqiansui_step。
        return tuple(step[0] for step in self.yangqiansui_steps(state))

    def yangqiansui_step(self, state):
        steps = self.yangqiansui_steps(state)
        idx = min(max(int(state.get("idx", 0)), 0), len(steps) - 1)
        return steps[idx]

    def yangqiansui_is_my_turn(self, state):
        return self.yangqiansui_step(state)[0] == type(self).__name__

    def _yangqiansui_advance_state(self, state):
        steps = self.yangqiansui_steps(state)
        state["idx"] += 1
        if state["idx"] >= len(steps):
            state["phase"] = "loop"
            state["idx"] = 0

    @staticmethod
    def _yangqiansui_char_matches_name(char, expected_name):
        if char is None:
            return False
        return any(cls.__name__ == expected_name for cls in type(char).mro())

    def _yangqiansui_expected_target(self, state):
        expected_name = self.yangqiansui_step(state)[0]
        for char in getattr(self.task, "chars", ()): 
            if self._yangqiansui_char_matches_name(char, expected_name):
                return char
        return None

    def _yangqiansui_fast_switch(self, state):
        """A/下落A后的极限换人：只发切换键，不让普通切人流程自动补 click。"""
        target = self._yangqiansui_expected_target(state)
        if target is None:
            self.logger.warning('YangqianSui fast-swap target not found; fallback to normal switch')
            return super().switch_next_char()

        next_actions = self.yangqiansui_step(state)[2]
        expected_intro = bool(next_actions and next_actions[0] == "intro")
        target.has_intro = expected_intro
        target.has_sub_dps_intro = expected_intro and getattr(self, "is_sub_dps", False)

        self.logger.info(
            f'YangqianSui fast-swap {type(self).__name__} -> {type(target).__name__} '
            f'expected_intro={expected_intro}'
        )

        start = time.time()
        last_send = -999.0
        while time.time() - start < self.AXIS_FAST_SWITCH_TIMEOUT:
            now = time.time()
            if now - last_send >= self.AXIS_FAST_SWITCH_RETRY:
                self.task.send_key(target.index + 1)
                last_send = now

            self.task.next_frame()
            in_team, current_index, _ = self.task.in_team()
            if in_team and current_index == target.index:
                self.task.in_liberation = False
                self.switch_out(con_full=expected_intro)
                target.is_current_char = True
                target.last_switch_in_time = time.time()
                if expected_intro:
                    current_time = time.time()
                    self.last_outro_time = current_time
                    add_freeze = getattr(self.task, "add_freeze_duration", None)
                    if add_freeze is not None:
                        add_freeze(current_time, target.intro_motion_freeze_duration, -100)
                return

        self.logger.warning('YangqianSui fast-swap timed out; fallback to normal switch')
        return super().switch_next_char()

    def yangqiansui_perform_step(self, state):
        """执行当前攻略节点，然后推进节点并切到下一位指定角色。"""
        char_name, label, actions = self.yangqiansui_step(state)
        if char_name != type(self).__name__:
            return self.switch_next_char()

        self.logger.info(
            f'YangqianSui {state["phase"]} step {state["idx"] + 1}: {char_name} {label}'
        )
        for pos, action in enumerate(actions):
            next_action = actions[pos + 1] if pos + 1 < len(actions) else None
            context = None
            if type(self).__name__ == "Chisa" and label == "aEa3":
                if pos == 0 and action == "a":
                    context = "chisa_entry_fall"
                elif action == "e":
                    context = "chisa_e_to_a3"
                elif pos == len(actions) - 1 and action == "a":
                    context = "chisa_a3_swap"

            self._yangqiansui_execute_action(
                action,
                is_last=(pos == len(actions) - 1),
                next_action=next_action,
                context=context,
            )

        # A / 下落A 接切人是这套轴的核心取消点：推进共享状态后直接走 fast-swap。
        if actions and actions[-1] in ("a", "fall_a"):
            self._yangqiansui_advance_state(state)
            return self._yangqiansui_fast_switch(state)

        return self.switch_next_char()

    def _yangqiansui_basic_gap(self):
        if type(self).__name__ == "Suisui":
            return self.AXIS_SUISUI_BASIC_GAP
        return self.AXIS_BASIC_GAP

    def _yangqiansui_suisui_a234(self):
        """启动轴专用：穗穗按 A2→A3→A4 节奏出手，并在 A4 后再交给 E。"""
        self.click()
        self._yangqiansui_gap(self.AXIS_SUISUI_A2_TO_A3_GAP)
        self.click()
        self._yangqiansui_gap(self.AXIS_SUISUI_A3_TO_A4_GAP)
        self.click()
        self._yangqiansui_gap(self.AXIS_SUISUI_A4_TO_E_GAP)

    def _yangqiansui_wait_airborne(self):
        """E 接下落攻击时等待角色进入空中。"""
        start = time.time()
        while time.time() - start < self.AXIS_AIRBORNE_TIMEOUT:
            self.task.next_frame()
            if self.flying():
                self.logger.debug('YangqianSui airborne confirmed before fall attack')
                return True
            self._yangqiansui_gap(self.AXIS_AIRBORNE_POLL)
        self.logger.warning('YangqianSui airborne detection timed out before fall attack')
        return False

    def _yangqiansui_execute_action(self, action, *, is_last=False, next_action=None, context=None):
        """把攻略图中的一个动作转换成 OKWW 输入。"""
        if action == "intro":
            if self.has_intro:
                self.wait_intro(time_out=self.AXIS_INTRO_TIMEOUT, click=False)
            else:
                self.logger.warning('YangqianSui expected intro but has_intro is false')
            return

        if action == "suisui_a234":
            self._yangqiansui_suisui_a234()
            return

        if action == "a":
            # 千咲 aEa3 的第一下 A 是接穗穗下落快切后的空中下落 A，不按普通平 A 节奏处理。
            if context == "chisa_entry_fall":
                self._yangqiansui_gap(self.AXIS_CHISA_SWITCH_TO_FALL_GAP)
                self.click()
                self._yangqiansui_gap(self.AXIS_CHISA_FALL_TO_E_GAP)
                return

            self.click()
            if is_last:
                gap = (self.AXIS_CHISA_A3_SWAP_GAP
                       if context == "chisa_a3_swap" else self.AXIS_ATTACK_SWAP_GAP)
                self._yangqiansui_gap(gap)
            else:
                self._yangqiansui_gap(self._yangqiansui_basic_gap())
            return

        if action == "e":
            self.send_resonance_key()
            self.record_resonance_use()
            if next_action == "fall_a":
                # flying 只说明已经离地，不代表 E 动画已经开放下落 A 输入；因此再留一小段可接窗口。
                self._yangqiansui_wait_airborne()
                self._yangqiansui_gap(self.AXIS_SUISUI_AIRBORNE_TO_FALL_GAP)
            elif context == "chisa_e_to_a3":
                self._yangqiansui_gap(self.AXIS_CHISA_E_TO_A3_GAP)
            else:
                self._yangqiansui_gap(
                    self.AXIS_ACTION_END_GAP if is_last else self.AXIS_SKILL_GAP
                )
            return

        if action == "e_if_no_signature":
            has_signature = True
            checker = getattr(self, "is_signature_weapon_config", None)
            if checker is not None:
                has_signature = bool(checker())
            if not has_signature:
                self.send_resonance_key()
                self.record_resonance_use()
                self._yangqiansui_gap(self.AXIS_SKILL_GAP)
            return

        if action == "q":
            self.send_echo_key()
            self.record_echo_use()
            self._yangqiansui_gap(self.AXIS_ACTION_END_GAP if is_last else self.AXIS_ECHO_GAP)
            return

        if action == "r":
            # R 会隐藏队伍 UI；用原生 helper 等动画结束，但关闭自动 F，F 在图里有明确节点。
            if not self.click_liberation(wait_if_cd_ready=0, click_f=False):
                self.logger.warning('YangqianSui liberation input was not confirmed')
            self._yangqiansui_gap(self.AXIS_ACTION_END_GAP)
            return

        if action == "z":
            self.heavy_attack(self.AXIS_HEAVY_DURATION)
            self._yangqiansui_gap(self.AXIS_ACTION_END_GAP)
            return

        if action == "f":
            self.task.send_key('f')
            self._yangqiansui_gap(self.AXIS_F_GAP)
            return

        if action == "w":
            self.task.send_key('w', down_time=self.AXIS_FORWARD_DURATION)
            self._yangqiansui_gap(self.AXIS_F_GAP)
            return

        if action == "fall_a":
            # 只等下落攻击起手，然后由 perform_step 直接 fast-swap；不等待落地。
            self.click()
            self._yangqiansui_gap(self.AXIS_FALL_TRIGGER_GAP)
            return

        raise ValueError(f"Unknown YangqianSui axis action: {action}")

    def _yangqiansui_gap(self, duration):
        if duration > 0:
            self.sleep(duration, check_combat=False)

    def switch_next_char(self, *args, **kwargs):
        # 非 fast-swap 节点仍走原生切人；在调用父类前先推进轴状态，确保 MUST 指向下一角色。
        state = self.yangqiansui_state()
        if state is not None and self.yangqiansui_is_my_turn(state):
            self._yangqiansui_advance_state(state)
        return super().switch_next_char(*args, **kwargs)
