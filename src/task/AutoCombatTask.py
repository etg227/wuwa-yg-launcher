import time

from ok import TriggerTask, Logger
from src.char.CharFactory import char_names
from src.scene.WWScene import WWScene
from src.task.BaseCombatTask import BaseCombatTask, NotInCombatException, CharDeadException

logger = Logger.get_logger(__name__)


class AutoCombatTask(BaseCombatTask, TriggerTask):
    owns_switch_healer_config = True

    # 内置固定轴对起手角色和切人顺序有明确要求，不能执行 OKWW 默认的
    # “开战先切治疗 / 战后切治疗”行为，否则会在第一个轴节点执行前破坏状态。
    BUILTIN_AXIS_TEAMS = {
        frozenset({"YangYangSp", "Chisa", "Suisui"}): "秧千穗轴",
        frozenset({"Aemeath", "Denia", "Chisa"}): "爱达千轴",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_config = {'_enabled': True}
        self.trigger_interval = 0.1
        self.name = "⚔️ Auto Combat"
        self.visible = False  # 触发页已移除，由椰果启动器页开关
        self.description = "Enable auto combat in Abyss, Game World etc"
        self.last_is_click = False
        self.default_config.update({
            'Auto Target': True,
            'Use Liberation': True,
            'Check Levitator': True,
            'Switch to Healer before and after Combat': True,
        })
        self.config_description = {
            'Auto Target': 'Turn off to enable auto combat only when manually target enemy using middle click',
            'Use Liberation': 'Do not use Liberation in Open World to Save Time',
            'Check Levitator': 'Toggle the levitator and verify if the character is floating',
            'Switch to Healer before and after Combat': 'Better Chance to Keep Character Alive',
        }
        self.op_index = 0
        self.char_features_warmed_up = False

    def warm_up_char_features(self):
        if self.char_features_warmed_up:
            return
        try:
            for char_name in char_names:
                self.get_feature_by_name(char_name)
        except Exception as e:
            logger.warning(f'warm_up_char_features failed: {e}')
            return
        self.char_features_warmed_up = True
        logger.info(f'warm_up_char_features loaded {len(char_names)} character templates')

    def _builtin_axis_name(self):
        """返回当前三人队对应的内置轴名称；未命中固定轴时返回 None。"""
        from src.char.JimoshouAxis import is_jimoshou_team

        # 忌莫守依赖固定 1/2/3 槽位，不能只用 frozenset 判断队伍组成。
        if is_jimoshou_team(self.chars):
            return "忌莫守轴"

        recognized = frozenset(type(char).__name__ for char in self.chars if char is not None)
        return self.BUILTIN_AXIS_TEAMS.get(recognized)

    def run(self):
        self.warm_up_char_features()
        ret = False
        if not self.scene.in_team(self.in_team_and_world):
            return ret
        self.use_liberation = self.config.get('Use Liberation')
        if not self.use_liberation and not self.in_world():  # 仅大世界生效
            self.use_liberation = True
        combat_start = time.time()
        switched_to_healer = False

        recognized_team = [type(char).__name__ if char is not None else "None" for char in self.chars]
        builtin_axis_name = self._builtin_axis_name()
        if builtin_axis_name:
            logger.info(
                f'AutoCombat detected builtin axis {builtin_axis_name}, team={recognized_team}; '
                f'skip healer switch before/after combat'
            )
        else:
            logger.info(f'AutoCombat recognized team={recognized_team}; no builtin axis matched')

        jimoshou_controller = None
        if builtin_axis_name == "忌莫守轴":
            from src.char.JimoshouAxis import JimoshouAxisController
            jimoshou_controller = JimoshouAxisController(self)

        while self.in_combat():
            ret = True
            try:
                if not switched_to_healer:
                    # 固定轴必须从攻略指定的起手角色开始。原生 switch_healer() 会在
                    # perform() 前切走起手角色，因此内置轴一律跳过这层安全切人。
                    if builtin_axis_name is None:
                        self.switch_healer()
                    switched_to_healer = True

                if jimoshou_controller is not None:
                    # 忌莫守宏段必须完全隔离角色 do_perform/helper；首次从 1 号忌炎起手，
                    # 循环收尾 EE→2→3 后由 controller 从守岸人的循环动作段继续。
                    if not jimoshou_controller.run_cycle():
                        logger.warning('Jimoshou axis stopped before cycle completion')
                        break
                else:
                    self.get_current_char().perform()
            except CharDeadException:
                self.log_error(f'Characters dead', notify=True)
                break
            except NotInCombatException as e:
                logger.info(f'auto_combat_task_out_of_combat {int(time.time() - combat_start)} {e}')
                break
        if ret:
            self.combat_end()
            # 战斗结束后同样不改动固定轴队伍的站场角色，避免下一场开局角色被提前改变。
            if builtin_axis_name is None:
                self.switch_healer()
        return ret

    def realm_perform(self):
        if not self.last_is_click:
            if self.op_index % 10 == 0:
                self.send_key_and_wait_animation('4', self.in_illusive_realm, enter_animation_wait=0.2)
            else:
                self.click()
        else:
            if self.available('liberation'):
                self.send_key_and_wait_animation(self.get_liberation_key(), self.in_illusive_realm)
            elif self.available('echo'):
                self.send_key(self.get_echo_key())
            elif self.available('resonance'):
                self.send_key(self.get_resonance_key())
            elif self.is_con_full() and self.in_team()[0]:
                self.send_key_and_wait_animation('2', self.in_illusive_realm)
        self.last_is_click = not self.last_is_click
        self.op_index += 1
        self.sleep(0.02)


from ok import run_task
from config import config

if __name__ == "__main__":
    run_task(config, task=AutoCombatTask, debug=True)
