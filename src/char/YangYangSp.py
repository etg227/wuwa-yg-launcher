import time

from ok import Logger
from src.char.BaseChar import BaseChar, SwitchPriority
from src.char.YangqianSuiAxis import YangqianSuiAxis


class YangYangSp(YangqianSuiAxis, BaseChar):
    INTRO_PERFORM_DURATION = 8.0
    PERFORM_DURATION = 3.2
    LONG_PRESS_RELEASE_DELAY = 0.1
    DISPLAY_NAME = 'Yangyang: Xuanling'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = Logger.get_logger(self.DISPLAY_NAME)

    @property
    def display_name(self):
        return self.DISPLAY_NAME

    def __repr__(self):
        return self.DISPLAY_NAME

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        state = self.yangqiansui_state()
        if state is not None:
            return SwitchPriority.MUST if self.yangqiansui_is_my_turn(state) else SwitchPriority.NO
        return super().get_switch_priority(current_char, has_intro, target_low_con)

    def do_perform(self):
        # 秧千穗轴命中时，不轮到自己出手就直接让位；轮到自己完全走原逻辑。
        state = self.yangqiansui_state()
        if state is not None and not self.yangqiansui_is_my_turn(state):
            return self.switch_next_char()
        duration = self.INTRO_PERFORM_DURATION if self.has_intro else self.PERFORM_DURATION
        start = time.time()
        self.task.mouse_down()
        resonance_available = 0
        echo_used = False
        try:
            while self.time_elapsed_accounting_for_freeze(start) < duration:
                if self.liberation_available():
                    self.logger.debug('liberation_available')
                    if not self.click_liberation(send_click=False, wait_if_cd_ready=0):
                        pass
                    else:
                        duration += 2
                elif self.resonance_available():
                    self.logger.debug('resonance_available')
                    if resonance_available == 0:
                        resonance_available = time.time()
                    if resonance_available != 0 and time.time() - resonance_available > 0.2:
                        self.logger.debug('resonance available for 0.2')
                        self.click_resonance(send_click=False, time_out=1)
                elif not echo_used:
                    resonance_available = 0
                    echo_used = self.click_echo(time_out=0)
                else:
                    resonance_available = 0
                self.sleep(0.05)
        finally:
            self.task.mouse_up()
            # Let the released heavy attack settle before another character reads
            # the shared long-action indicator.
            self.sleep(self.LONG_PRESS_RELEASE_DELAY, check_combat=False)
        self.switch_next_char()
