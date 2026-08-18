"""爱达千内置轴（爱弥斯 / 达妮娅 / 千咲）：纯粹的出场顺序协同。

不重写任何角色自身的技能释放逻辑——三个角色的 do_perform 完全是 okww
原生代码（perform_everything / lib1-lib2 状态机 / 支援-输出双模式等），
本文件只做一件事：按用户给出的出手顺序，在恰当的时候把 MUST 优先级交
给该上场的角色，让框架原生的 switch_next_char/_choose_switch_target 完
成实际切人。是否要打大招二段、要不要进入千咲的爆发状态，都由角色自己
的状态判断决定，不在这里代为决定。
"""

AXIS_TEAM = ("Aemeath", "Denia", "Chisa")

# 出手顺序（按用户提供的正确手法整理，仅记录“轮到谁”，不记录具体按键）。
# 达妮娅先手；千咲/爱弥斯的每一轮是长是短，由各自角色代码内部状态
# （协奏、大招二段、真数满等）决定，这里不做区分。
OPENER_ORDER = (
    "Denia", "Chisa", "Denia", "Chisa", "Denia", "Chisa",
    "Aemeath", "Chisa", "Aemeath", "Chisa", "Aemeath",
)
LOOP_ORDER = (
    "Aemeath", "Chisa", "Aemeath", "Chisa", "Denia", "Aemeath", "Denia",
    "Chisa", "Denia", "Chisa", "Denia", "Aemeath", "Chisa", "Aemeath",
    "Denia", "Aemeath",
)

# 椰果启动器页展示的内置轴登记表。
BUILTIN_AXES = (
    {
        "name": "爱达千轴",
        "team": "爱弥斯 / 达妮娅(先手) / 千咲",
        "first": "达妮娅先手；启动轴打完自动进入循环轴，直到战斗结束",
        "description": "只协同出场顺序，技能释放、大招二段、真数满切人等完全由角色自身逻辑判断；"
                       "上阵该队伍并开启自动战斗即生效，无需额外操作。",
    },
)


class AidaqianAxis:
    """爱达千出场顺序协同 mixin：与 BaseChar 子类多重继承使用。"""

    def in_aidaqian_team(self):
        task = self.task
        if task is None or not hasattr(task, "has_char"):
            return False
        from src.char.Aemeath import Aemeath
        from src.char.Chisa import Chisa
        from src.char.Denia import Denia
        return bool(task.has_char(Aemeath) and task.has_char(Denia) and task.has_char(Chisa))

    def aidaqian_state(self):
        if not self.in_aidaqian_team():
            return None
        task = self.task
        combat_start = getattr(task, "combat_start", 0) or 0
        state = getattr(task, "_aidaqian_axis", None)
        if not isinstance(state, dict) or state.get("combat_start") != combat_start:
            state = {"combat_start": combat_start, "phase": "opener", "idx": 0}
            task._aidaqian_axis = state
        return state

    def aidaqian_order(self, state):
        return OPENER_ORDER if state["phase"] == "opener" else LOOP_ORDER

    def aidaqian_is_my_turn(self, state):
        return self.aidaqian_order(state)[state["idx"]] == type(self).__name__

    # do_perform / get_switch_priority 故意不在这个 mixin 里实现：角色类自己
    # 已经有原生的 do_perform / (Denia 的) get_switch_priority，多重继承下让
    # mixin 代管这两个方法会让 super() 链路指向错误的下一个类，且千咲还同时
    # 混入了 YangqianSuiAxis，两边队伍要分开判断。改为角色类自己在方法开头
    # 调用 aidaqian_state()/aidaqian_is_my_turn() 这两个纯辅助方法。

    def switch_next_char(self, *args, **kwargs):
        # 角色自身逻辑判定"这轮打完了"时会调用这个方法；轮到的人才推进顺序指针，
        # 顺序指针推进必须先于父类真正切人，这样 get_switch_priority 才能在
        # 同一次切人里立刻看到下一个该上场的角色。
        state = self.aidaqian_state()
        if state is not None and self.aidaqian_is_my_turn(state):
            order = self.aidaqian_order(state)
            state["idx"] += 1
            if state["idx"] >= len(order):
                state["phase"] = "loop"
                state["idx"] = 0
        return super().switch_next_char(*args, **kwargs)
