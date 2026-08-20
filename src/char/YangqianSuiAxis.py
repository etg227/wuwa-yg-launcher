"""秧千穗 25s 双羽内置轴（秧秧 / 千咲 / 穗穗）。

这支轴不能只靠“轮到谁上场”来复现。原图里大量使用拆普攻段、快速换人、
变奏后立刻接技能等操作，因此这里把启动轴与循环轴都记录成“角色 + 明确动作”
节点。角色命中这支队伍时直接执行当前节点；不再让通用 do_perform 自己决定
这一轮要打什么。

动作记号沿用攻略图：
- a：一次普攻输入；a123 / a234 等在节点里展开成多次 a
- E：共鸣技能；Q：声骸；R：共鸣解放；Z：重击；F：F 键
- W：短按向前；下落a：空中普攻并等待落地
- 变：该节点预期由变奏入场；只做入场同步，不主动伪造协奏/变奏

目前没有攻略作者的毫秒宏时间戳，因此极限取消窗口先使用一组很短、集中在本
文件的保守间隔。后续拿到宏时间戳时只需要替换这些间隔，不必再改轴结构。
"""

AXIS_TEAM = ("YangYangSp", "Chisa", "Suisui")

# step = (角色类名, 图中标签, 动作元组)
OPENER_STEPS = (
    ("YangYangSp", "E", ("e",)),
    ("Suisui", "a234E下落a", ("a", "a", "a", "e", "fall_a")),
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

    # 没有宏毫秒时间戳时的第一版输入间隔。全部集中在这里便于实机微调。
    AXIS_BASIC_GAP = 0.18
    AXIS_SKILL_GAP = 0.12
    AXIS_ECHO_GAP = 0.10
    AXIS_F_GAP = 0.06
    AXIS_LAST_INPUT_GAP = 0.06
    AXIS_HEAVY_DURATION = 0.60
    AXIS_FORWARD_DURATION = 0.18
    AXIS_INTRO_TIMEOUT = 1.35

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

    def yangqiansui_perform_step(self, state):
        """执行当前攻略节点，然后推进节点并切到下一位指定角色。"""
        char_name, label, actions = self.yangqiansui_step(state)
        if char_name != type(self).__name__:
            return self.switch_next_char()

        self.logger.info(
            f'YangqianSui {state["phase"]} step {state["idx"] + 1}: {char_name} {label}'
        )
        for pos, action in enumerate(actions):
            self._yangqiansui_execute_action(action, is_last=(pos == len(actions) - 1))
        return self.switch_next_char()

    def _yangqiansui_execute_action(self, action, *, is_last=False):
        """把攻略图中的一个动作转换成 OKWW 输入。"""
        if action == "intro":
            if self.has_intro:
                # 不在变奏动画期间连点，避免把后续轴输入提前吃掉。
                self.wait_intro(time_out=self.AXIS_INTRO_TIMEOUT, click=False)
            else:
                self.logger.warning('YangqianSui expected intro but has_intro is false')
            return

        if action == "a":
            self.click()
            self._yangqiansui_gap(self.AXIS_LAST_INPUT_GAP if is_last else self.AXIS_BASIC_GAP)
            return

        if action == "e":
            # 固定轴优先忠实发送输入，而不是让通用角色 AI 再决定技能是否值得放。
            self.send_resonance_key()
            self.record_resonance_use()
            self._yangqiansui_gap(self.AXIS_LAST_INPUT_GAP if is_last else self.AXIS_SKILL_GAP)
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
            self._yangqiansui_gap(self.AXIS_LAST_INPUT_GAP if is_last else self.AXIS_ECHO_GAP)
            return

        if action == "r":
            # R 会隐藏队伍 UI；用原生 helper 等动画结束，但关闭自动 F，F 在图里有明确节点。
            if not self.click_liberation(wait_if_cd_ready=0, click_f=False):
                self.logger.warning('YangqianSui liberation input was not confirmed')
            self._yangqiansui_gap(self.AXIS_LAST_INPUT_GAP)
            return

        if action == "z":
            self.heavy_attack(self.AXIS_HEAVY_DURATION)
            self._yangqiansui_gap(self.AXIS_LAST_INPUT_GAP)
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
            # 图中明确写“下落a”：只按一次空中普攻，随后等待落地，不连续补 A。
            self.click()
            self._yangqiansui_gap(0.08)
            self.wait_down(click=False)
            self._yangqiansui_gap(self.AXIS_LAST_INPUT_GAP)
            return

        raise ValueError(f"Unknown YangqianSui axis action: {action}")

    def _yangqiansui_gap(self, duration):
        if duration > 0:
            # 轴内的短间隔不因为大招/切人暂时隐藏目标 UI 而误判战斗结束。
            self.sleep(duration, check_combat=False)

    def switch_next_char(self, *args, **kwargs):
        # 当前节点完整结束后先推进 state，让同一次原生 switch_next_char 立即看到
        # 下一节点角色的 MUST 优先级。
        state = self.yangqiansui_state()
        if state is not None and self.yangqiansui_is_my_turn(state):
            steps = self.yangqiansui_steps(state)
            state["idx"] += 1
            if state["idx"] >= len(steps):
                state["phase"] = "loop"
                state["idx"] = 0
        return super().switch_next_char(*args, **kwargs)
