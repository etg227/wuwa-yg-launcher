import time

from src.char.AidaqianAxis import AidaqianAxis
from src.char.BaseChar import BaseChar, CharType, SwitchPriority, get_default_buff_time
from src.char.YangqianSuiAxis import YangqianSuiAxis


class Chisa(AidaqianAxis, YangqianSuiAxis, BaseChar):
    SUPPORT_ACTION_DURATION = 1.2
    SUPPORT_LONG_ACTION_DURATION = 10.0
    INTRO_NORMAL_ATTACK_DURATION = 2.0

    def is_dps_config(self):
        return self.task and self.task.char_config.get("Chisa DPS")

    def get_char_type(self):
        if self.is_dps_config():
            return CharType.MAIN_DPS
        return super().get_char_type()

    def get_buff_time(self):
        if self.is_dps_config():
            return get_default_buff_time(CharType.MAIN_DPS)
        return super().get_buff_time()

    def do_perform(self):
        # 千咲同时在两支队伍的轴里都有协同角色；命中哪支队伍就用哪边的顺序，
        # 不轮到自己出手就直接让位，轮到自己（或都没命中）完全走原逻辑。
        a_state = self.aidaqian_state()
        if a_state is not None:
            if not self.aidaqian_is_my_turn(a_state):
                return self.switch_next_char()
        else:
            y_state = self.yangqiansui_state()
            if y_state is not None and not self.yangqiansui_is_my_turn(y_state):
                return self.switch_next_char()
        if self.is_dps_config():
            return self.do_dps_perform()
        return self.do_support_perform()

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        a_state = self.aidaqian_state()
        if a_state is not None:
            return SwitchPriority.MUST if self.aidaqian_is_my_turn(a_state) else SwitchPriority.NO
        y_state = self.yangqiansui_state()
        if y_state is not None:
            return SwitchPriority.MUST if self.yangqiansui_is_my_turn(y_state) else SwitchPriority.NO
        return super().get_switch_priority(current_char, has_intro, target_low_con)

    def do_support_perform(self):
        needs_long_actions = self.has_intro and not self.has_buff()
        if self.has_intro:
            self.continues_normal_attack(self.INTRO_NORMAL_ATTACK_DURATION)

        duration = (self.SUPPORT_LONG_ACTION_DURATION
                    if needs_long_actions else self.SUPPORT_ACTION_DURATION)
        if self.flying() and not self.liberation_available() and not self.resonance_available():
            self.wait_down()
        self.click_echo(time_out=0)

        start = time.time()
        while self.time_elapsed_accounting_for_freeze(start) < duration:
            self.cycle_start()
            if self.is_con_full():
                return self.switch_next_char()
            if self.liberation_available():
                self.click_liberation(wait_if_cd_ready=0)
            elif self.is_forte_full():
                if self.perform_forte():
                    break
            elif self.click_resonance(time_out=0)[0]:
                pass
            else:
                self.click()
            self.cycle_sleep()

        return self.switch_next_char()

    def do_dps_perform(self):
        timeout = 2.5
        self.check_f_on_switch = True
        if self.has_intro:
            self.continues_normal_attack(0.8)
            timeout = 2.3
        if self.flying() and not self.liberation_available() and not self.resonance_available():
            self.wait_down()
        self.click_echo()
        start = time.time()
        under_liber = False
        while time.time() - start < timeout:
            if time.time() - start < 0.5 and self.click_liberation():
                start = time.time()
                under_liber = True
                timeout = 10
                self.sleep(0.2)
            if time.time() - start < 0.5 and not self.is_forte_full() and self.click_resonance()[0]:
                start = time.time()
                if timeout != 10:
                    timeout = 1.7
            if (under_liber or self.is_dps_config()) and self.is_forte_full() and self.perform_forte():
                self.check_f_on_switch = False
                return self.switch_next_char()
            self.click()
            self.check_combat()
            self.task.next_frame()
        self.switch_next_char()

    def perform_forte(self):
        if self.flying():
            self.wait_down()
        self.task.send_key(self.get_resonance_key(), down_time=1.2)
        if self.is_forte_full():
            return False
        self.heavy_attack(3.5)
        return True
