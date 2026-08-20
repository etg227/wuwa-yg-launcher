import unittest

from src.char.YangqianSuiAxis import LOOP_STEPS, OPENER_STEPS


class TestYangqianSuiAxis(unittest.TestCase):
    def test_opener_matches_guide_order_and_actions(self):
        self.assertEqual(
            [(char, label) for char, label, _ in OPENER_STEPS],
            [
                ("YangYangSp", "E"),
                ("Suisui", "a234E下落a"),
                ("Chisa", "aEa3"),
                ("Suisui", "a123"),
                ("Chisa", "a4"),
                ("YangYangSp", "aE"),
                ("Suisui", "a4QR"),
                ("Chisa", "变QRE"),
                ("YangYangSp", "a123"),
                ("Chisa", "Z"),
                ("YangYangSp", "a12Q"),
                ("Chisa", "a"),
                ("YangYangSp", "变EZREFW EZ"),
            ],
        )
        self.assertEqual(OPENER_STEPS[1][2], ("a", "a", "a", "e", "fall_a"))
        self.assertEqual(
            OPENER_STEPS[-1][2],
            ("intro", "e", "z", "r", "e", "f", "w", "e", "z"),
        )

    def test_loop_matches_guide_and_keeps_conditional_suisui_e(self):
        self.assertEqual(len(LOOP_STEPS), 12)
        self.assertEqual(LOOP_STEPS[0], ("Suisui", "变下落a", ("intro", "fall_a")))
        self.assertEqual(
            LOOP_STEPS[5],
            ("Suisui", "a4(E条件)QR", ("a", "e_if_no_signature", "q", "r")),
        )
        self.assertEqual(LOOP_STEPS[-1][0], "YangYangSp")
