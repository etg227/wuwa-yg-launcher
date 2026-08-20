import unittest

from src.char.JimoshouAxis import (
    FINISHER_MACRO,
    JIYAN_ULT_DURATION_MS,
    STARTUP_MACRO,
    is_jimoshou_team,
)
from src.combat.RawInputTimeline import compile_raw_timeline


class TestJimoshouAxis(unittest.TestCase):
    def test_team_requires_exact_slot_order(self):
        Jiyan = type("Jiyan", (), {})
        Mortefi = type("Mortefi", (), {})
        ShoreKeeper = type("ShoreKeeper", (), {})

        self.assertTrue(is_jimoshou_team([Jiyan(), Mortefi(), ShoreKeeper()]))
        self.assertFalse(is_jimoshou_team([ShoreKeeper(), Mortefi(), Jiyan()]))
        self.assertFalse(is_jimoshou_team([Jiyan(), ShoreKeeper(), Mortefi()]))

    def test_startup_macro_keeps_verified_raw_timeline(self):
        schedule = compile_raw_timeline(STARTUP_MACRO)

        self.assertEqual(60, len(schedule))
        self.assertEqual(("key", "2", "down", 78), (
            schedule[0].event.device,
            schedule[0].event.code,
            schedule[0].event.action,
            schedule[0].event.delay_after_ms,
        ))

        # 8.9 秒 probe 的最后一个实际输入必须保持在同一个绝对时间点，
        # 这样扩展完整宏不会改变已经实机验证通过的前半段。
        self.assertEqual(8909, schedule[35].at_ms)
        self.assertEqual("mouse", schedule[35].event.device)
        self.assertEqual("left", schedule[35].event.code)
        self.assertEqual("up", schedule[35].event.action)

        # 完整启动宏最终停在忌炎 R 抬起；最后的 11000ms 交给独立大招输出阶段。
        self.assertEqual(15452, schedule[-1].at_ms)
        self.assertEqual("key", schedule[-1].event.device)
        self.assertEqual("r", schedule[-1].event.code)
        self.assertEqual("up", schedule[-1].event.action)
        self.assertEqual(JIYAN_ULT_DURATION_MS, schedule[-1].event.delay_after_ms)

    def test_finisher_uses_double_e_then_slot_three(self):
        down_codes = [
            event.code
            for event in FINISHER_MACRO
            if event.device == "key" and event.action == "down"
        ]
        self.assertEqual(["e", "e", "3"], down_codes)


if __name__ == "__main__":
    unittest.main()
