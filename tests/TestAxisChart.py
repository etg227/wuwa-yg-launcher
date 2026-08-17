import json
import unittest

from src.axis.AxisChart import (
    AxisChart,
    AxisFormatError,
    build_default_output_mapping,
    extract_community_id,
    normalize_axis_binding,
    parse_output_binding,
)


def create_axis_payload():
    return {
        "type": "wwcombo-chart",
        "version": 3,
        "chart": {
            "id": "wwc_test",
            "title": "测试轴",
            "startTriggerMoveId": "start_challenge",
            "steps": [
                {
                    "id": "step_1",
                    "moveId": "skill",
                    "label": "技能",
                    "characterSlot": 2,
                    "lane": "main",
                    "startMin": 100,
                    "startMax": 200,
                    "durationMin": 20,
                    "durationMax": 40,
                    "samples": [{"recordingId": "initial", "startTime": 123.5, "duration": 30.5}],
                },
                {
                    "id": "step_2",
                    "moveId": "dodge_hold",
                    "label": "长按闪避",
                    "startMin": 500,
                    "startMax": 500,
                    "durationMin": 200,
                    "durationMax": 200,
                    "samples": [],
                },
            ],
        },
        "moves": [
            {"id": "start_challenge", "label": "开始"},
            {"id": "skill", "label": "技能"},
            {"id": "dodge_hold", "label": "长按闪避"},
        ],
        "bindings": [
            {"moveId": "start_challenge", "inputs": [{"code": "KeyF", "label": "F"}]},
            {"moveId": "skill", "inputs": [{"code": "KeyE", "label": "E"}]},
            {
                "moveId": "dodge_hold",
                "inputs": [
                    {"code": "MouseRightHoid", "label": "MouseRightHoid"},
                    {"code": "Mouse4", "label": "Mouse4"},
                ],
            },
        ],
    }


class TestAxisChart(unittest.TestCase):
    def test_parse_wwcombo_v3_uses_initial_sample_and_range_fallback(self):
        chart = AxisChart.from_json(json.dumps(create_axis_payload()))

        self.assertEqual(chart.title, "测试轴")
        self.assertEqual(len(chart.steps), 2)
        self.assertEqual(chart.steps[0].start_ms, 123.5)
        self.assertEqual(chart.steps[0].duration_ms, 30.5)
        self.assertEqual(chart.steps[1].start_ms, 500)
        self.assertEqual(chart.steps[1].duration_ms, 200)

    def test_default_mapping_uses_local_hotkeys_for_semantic_actions(self):
        chart = AxisChart.from_dict(create_axis_payload())
        mapping = build_default_output_mapping(chart, {"Resonance Key": "x", "Dodge Key": "rshift"})

        self.assertEqual(mapping["skill"].config_text, "x")
        self.assertEqual(mapping["dodge_hold"].config_text, "rshift:hold")
        self.assertEqual(mapping["start_challenge"].config_text, "f")

    def test_hold_skill_uses_local_resonance_key(self):
        payload = create_axis_payload()
        payload["chart"]["steps"].append(
            {
                "id": "step_hold_skill",
                "moveId": "custom_hold_skill",
                "label": "长按技能",
                "startMin": 700,
                "startMax": 700,
                "durationMin": 500,
                "durationMax": 500,
                "samples": [],
            }
        )
        chart = AxisChart.from_dict(payload)

        default_mapping = build_default_output_mapping(chart)
        custom_mapping = build_default_output_mapping(chart, {"Resonance Key": "x"})

        self.assertEqual(default_mapping["custom_hold_skill"].config_text, "e:hold")
        self.assertEqual(custom_mapping["custom_hold_skill"].config_text, "x:hold")

    def test_legacy_mouse_right_typo_is_supported(self):
        binding = normalize_axis_binding("MouseRightHoid")

        self.assertEqual(binding.config_text, "mouse:right:hold")

    def test_empty_move_is_recognized_as_noop(self):
        payload = create_axis_payload()
        payload["chart"]["steps"].append(
            {
                "id": "step_empty",
                "moveId": "custom_empty",
                "label": "空招式",
                "startMin": 700,
                "startMax": 700,
                "durationMin": 100,
                "durationMax": 100,
                "samples": [],
            }
        )
        chart = AxisChart.from_dict(payload)

        self.assertTrue(chart.is_noop_move("custom_empty"))
        self.assertIsNone(build_default_output_mapping(chart)["custom_empty"])

    def test_unknown_unmapped_move_is_not_silently_treated_as_noop(self):
        payload = create_axis_payload()
        payload["chart"]["steps"].append(
            {
                "id": "step_unknown",
                "moveId": "custom_action",
                "label": "自定义动作",
                "startMin": 700,
                "startMax": 700,
                "durationMin": 100,
                "durationMax": 100,
                "samples": [],
            }
        )
        chart = AxisChart.from_dict(payload)

        self.assertFalse(chart.is_noop_move("custom_action"))

    def test_extract_community_id_from_download_url(self):
        result = extract_community_id(
            "https://nova.fb520.site/api/community/download/wwc_7dd8fdd2-44ce-4281-82e2-f03a3466bf30"
        )

        self.assertEqual(result, "wwc_7dd8fdd2-44ce-4281-82e2-f03a3466bf30")

    def test_rejects_non_wwcombo_json(self):
        with self.assertRaises(AxisFormatError):
            AxisChart.from_json('{"type": "unknown"}')

    def test_rejects_unsupported_manual_key_name(self):
        with self.assertRaises(AxisFormatError):
            parse_output_binding("not_a_real_key")


if __name__ == "__main__":
    unittest.main()
