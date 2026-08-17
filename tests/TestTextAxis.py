import unittest

from src.axis.AxisChart import AxisFormatError, build_default_output_mapping
from src.axis.TextAxis import parse_text_axis


class TestTextAxis(unittest.TestCase):
    def test_parses_switch_attack_counts_and_skills(self):
        chart, loop_start = parse_text_axis("1 a3 e")

        self.assertIsNone(loop_start)
        self.assertEqual(
            [step.move_id for step in chart.steps],
            ["switch_1", "basic_attack", "basic_attack", "basic_attack", "skill"],
        )

    def test_loop_marker_records_following_step(self):
        _, loop_start = parse_text_axis("a 循环 e r")

        self.assertEqual(loop_start, 1)

    def test_chinese_aliases_and_waits(self):
        chart, _ = parse_text_axis("切2 普 重 等0.5")
        self.assertEqual(chart.steps[2].move_id, "heavy_attack")

        self.assertEqual(
            [step.move_id for step in chart.steps],
            ["switch_2", "basic_attack", "heavy_attack", "noop"],
        )
        self.assertEqual(chart.steps[2].duration_ms, 600.0)
        self.assertEqual(chart.steps[3].duration_ms, 500.0)
        self.assertTrue(chart.is_noop_move("noop"))

    def test_heavy_attack_custom_duration(self):
        chart, _ = parse_text_axis("z1.2")

        self.assertEqual(chart.steps[0].move_id, "heavy_attack")
        self.assertEqual(chart.steps[0].duration_ms, 1200.0)

    def test_skill_hold_duration_and_mapping(self):
        chart, _ = parse_text_axis("e1.5 e")
        mappings = build_default_output_mapping(chart)

        self.assertEqual(chart.steps[0].move_id, "skill_hold")
        self.assertEqual(chart.steps[0].duration_ms, 1500.0)
        self.assertEqual(chart.steps[1].move_id, "skill")
        self.assertEqual(mappings["skill_hold"].config_text, "e:hold")
        self.assertEqual(mappings["skill"].config_text, "e")

    def test_comments_are_ignored(self):
        chart, _ = parse_text_axis("a # 起手\ne")

        self.assertEqual([step.move_id for step in chart.steps], ["basic_attack", "skill"])

    def test_default_mapping_covers_all_semantic_moves(self):
        chart, _ = parse_text_axis("1 2 3 a e e1.5 q r d j z f w1")
        mappings = build_default_output_mapping(chart)

        unmapped = [move_id for move_id, binding in mappings.items() if binding is None]
        # 只有空招式允许没有输出。
        self.assertEqual(unmapped, ["noop"])
        self.assertEqual(mappings["f_key"].config_text, "f")

    def test_invalid_inputs_raise_format_error(self):
        for text in ("", "x", "h", "a 循环", "循环 a 循环 e", "w0", "e0.05"):
            with self.assertRaises(AxisFormatError, msg=text):
                parse_text_axis(text)


if __name__ == "__main__":
    unittest.main()
