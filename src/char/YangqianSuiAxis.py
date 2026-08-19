"""秧千穗内置轴（秧秧 / 千咲 / 穗穗）：纯粹的出场顺序协同。

和爱达千轴（见 AidaqianAxis.py）同样的做法：不重写任何角色自身的技能释
放逻辑，三个角色的 do_perform 完全是 okww 原生代码。这里只做一件事：
按"猫眼石攻略组"秧千穗 25s 双羽轴整理出的出手顺序，在恰当的时候把 MUST
优先级交给该上场的角色，让框架原生的 switch_next_char/_choose_switch_
target 完成实际切人；具体这一轮打多久、要不要进入千咲的变奏状态，都由
角色自己的状态判断决定，不在这里代为决定。

穗穗（Suisui）是否持有专武是唯一需要额外代码的地方：没有专武时循环轴
里要多打一个 E，通过角色配置里的"Suisui Signature Weapon"开关控制，
在 Suisui.py 里读取。
"""

AXIS_TEAM = ("YangYangSp", "Chisa", "Suisui")

# 出手顺序：只记录"轮到谁"，不记录具体按键，具体动作由角色自身逻辑决定。
# 秧秧（1号位，蓝白）先手在场；启动轴打完自动进入循环轴，直到战斗结束。
# 每个角色最后一轮（下标 len-1）是该角色的"变奏"大招轮，其余都是短促的
# 单个技能/几下普攻就立刻切人，这个差异由 YangYangSp.py/Suisui.py 里按
# 下标识别，不在这里处理。
OPENER_ORDER = (
    "YangYangSp", "Suisui", "Chisa", "Suisui", "Chisa",
    "YangYangSp", "Suisui", "Chisa", "YangYangSp", "Chisa",
    "YangYangSp", "Chisa", "YangYangSp",
)
LOOP_ORDER = (
    "Suisui", "Chisa", "Suisui", "Chisa", "YangYangSp",
    "Suisui", "Chisa", "YangYangSp", "Chisa", "YangYangSp",
    "Chisa", "YangYangSp",
)

# 椰果启动器页展示的内置轴登记表条目（追加进 AxisControlTab 引用的列表）。
# char_config_switches 里的开关直接显示在这张卡片上，点了立即写入角色配置，
# 和"角色设置"页是同一份配置，两边同步。
BUILTIN_AXIS_ENTRY = {
    "name": "秧千穗轴",
    "team": "秧秧 / 千咲 / 穗穗",
    "first": "秧秧先手；启动轴打完自动进入循环轴，直到战斗结束",
    "description": "只协同出场顺序，技能释放完全由角色自身逻辑判断；"
                   "上阵该队伍并开启自动战斗即生效，无需额外操作。",
    "char_config_switches": (
        {"key": "Suisui Signature Weapon", "default": True, "label": "穗穗（Suisui）拥有专武"},
    ),
}


class YangqianSuiAxis:
    """秧千穗出场顺序协同 mixin：与 BaseChar 子类多重继承使用。"""

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

    def yangqiansui_order(self, state):
        return OPENER_ORDER if state["phase"] == "opener" else LOOP_ORDER

    def yangqiansui_is_my_turn(self, state):
        return self.yangqiansui_order(state)[state["idx"]] == type(self).__name__

    # do_perform / get_switch_priority 不在这个 mixin 里实现，原因同
    # AidaqianAxis：多重继承下让 mixin 代管这两个方法会让 super() 链路指向
    # 错误的下一个类，且千咲同时混入两个队伍的 mixin，两边必须分开判断。
    # 角色类自己在方法开头调用 yangqiansui_state()/yangqiansui_is_my_turn()。

    def switch_next_char(self, *args, **kwargs):
        # 角色自身逻辑判定"这轮打完了"时会调用这个方法；轮到的人才推进顺序指针。
        # 战前框架自带的"没有治疗就先切治疗"安全机制会把当前角色切到穗穗，
        # 但不需要为此单独处理：穗穗上场后 do_perform 发现不轮到自己会立刻
        # 再让位，一步之内自然接上正确的秧秧先手，跟爱达千轴是同一个道理。
        state = self.yangqiansui_state()
        if state is not None and self.yangqiansui_is_my_turn(state):
            order = self.yangqiansui_order(state)
            state["idx"] += 1
            if state["idx"] >= len(order):
                state["phase"] = "loop"
                state["idx"] = 0
        return super().switch_next_char(*args, **kwargs)
