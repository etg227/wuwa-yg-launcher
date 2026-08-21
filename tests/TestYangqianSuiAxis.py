"""秧千穗轴的行为测试。

不再逐条抄写 OPENER_STEPS/LOOP_STEPS 常量表（那种测试改轴必红、轴错仍绿），
而是直接驱动真实的 yangqiansui_perform_step / _yangqiansui_execute_action /
_yangqiansui_advance_state，验证：

- 轴表里的每个节点都能被当前执行器完整执行（未知动作 token 立即暴露）；
- 状态机推进正确：启动轴打完滚入循环轴、循环轴回绕、越界 idx 不崩；
- 每执行一个节点，共享状态恰好推进一格，且总会发起一次切人；
- e_if_no_signature 只在穗穗无专武时补 E。

替身只模拟 BaseChar 的输入方法，不依赖 ok 框架，可在无 GUI 环境运行。
"""

import unittest

from src.char.YangqianSuiAxis import (
    AXIS_TEAM,
    LOOP_STEPS,
    OPENER_STEPS,
    YangqianSuiAxis,
)


class _SilentLogger:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


class _FakeTask:
    def next_frame(self):
        pass

    def send_key(self, key, down_time=None):
        pass


class _RecordingBase:
    """BaseChar 的最小替身：记录轴混入实际发出的输入与切人调用。"""

    def __init__(self):
        self.calls = []
        self.has_intro = True
        self.task = _FakeTask()
        self.logger = _SilentLogger()

    def click(self):
        self.calls.append("click")

    def send_resonance_key(self):
        self.calls.append("resonance")

    def record_resonance_use(self):
        pass

    def send_echo_key(self):
        self.calls.append("echo")

    def record_echo_use(self):
        pass

    def click_liberation(self, **kwargs):
        self.calls.append("liberation")
        return True

    def heavy_attack(self, duration):
        self.calls.append("heavy")

    def wait_intro(self, **kwargs):
        self.calls.append("wait_intro")

    def flying(self):
        return True

    def sleep(self, duration, check_combat=True):
        pass

    def switch_next_char(self, *args, **kwargs):
        self.calls.append("normal_switch")


def _make_stub(char_name, state=None):
    """构造类名为 char_name 的轴替身；state 直接注入，绕过 ok 队伍识别。"""

    def fake_state(self):
        return state

    def fake_fast_switch(self, _state):
        self.calls.append("fast_switch")

    cls = type(
        char_name,
        (YangqianSuiAxis, _RecordingBase),
        {
            "yangqiansui_state": fake_state,
            "_yangqiansui_fast_switch": fake_fast_switch,
        },
    )
    return cls()


def _all_steps():
    for idx, step in enumerate(OPENER_STEPS):
        yield "opener", idx, step
    for idx, step in enumerate(LOOP_STEPS):
        yield "loop", idx, step


class TestAxisChartIntegrity(unittest.TestCase):
    def test_steps_only_use_team_chars(self):
        for phase, idx, (char_name, label, _) in _all_steps():
            self.assertIn(
                char_name, AXIS_TEAM,
                f"{phase}[{idx}] {label} 指定了不在队伍里的角色 {char_name}",
            )

    def test_intro_only_appears_as_first_action(self):
        for phase, idx, (char_name, label, actions) in _all_steps():
            for pos, action in enumerate(actions):
                if action == "intro":
                    self.assertEqual(
                        pos, 0,
                        f"{phase}[{idx}] {label}: 变奏入场只能是节点的第一个动作",
                    )

    def test_unknown_action_raises(self):
        stub = _make_stub("Suisui")
        with self.assertRaises(ValueError):
            stub._yangqiansui_execute_action("no_such_action")


class TestAxisStateMachine(unittest.TestCase):
    def test_opener_rolls_into_loop(self):
        stub = _make_stub("Suisui")
        state = {"phase": "opener", "idx": len(OPENER_STEPS) - 1}
        stub._yangqiansui_advance_state(state)
        self.assertEqual(state, {"phase": "loop", "idx": 0})

    def test_loop_wraps_to_start(self):
        stub = _make_stub("Suisui")
        state = {"phase": "loop", "idx": len(LOOP_STEPS) - 1}
        stub._yangqiansui_advance_state(state)
        self.assertEqual(state, {"phase": "loop", "idx": 0})

    def test_step_clamps_out_of_range_idx(self):
        stub = _make_stub("Suisui")
        self.assertEqual(
            stub.yangqiansui_step({"phase": "opener", "idx": 999}),
            OPENER_STEPS[-1],
        )
        self.assertEqual(
            stub.yangqiansui_step({"phase": "opener", "idx": -3}),
            OPENER_STEPS[0],
        )

    def test_is_my_turn_matches_step_char(self):
        state = {"phase": "opener", "idx": 0}
        expected = OPENER_STEPS[0][0]
        self.assertTrue(_make_stub(expected, state).yangqiansui_is_my_turn(state))
        other = next(name for name in AXIS_TEAM if name != expected)
        self.assertFalse(_make_stub(other, state).yangqiansui_is_my_turn(state))


class TestPerformStep(unittest.TestCase):
    def test_every_step_executes_and_advances_exactly_one_node(self):
        """逐节点执行真实 perform_step：动作 token 全部可执行，状态恰好前进一格。"""
        for phase, idx, (char_name, label, _) in _all_steps():
            with self.subTest(phase=phase, idx=idx, label=label):
                state = {"phase": phase, "idx": idx}
                stub = _make_stub(char_name, state)
                stub.yangqiansui_perform_step(state)

                steps = OPENER_STEPS if phase == "opener" else LOOP_STEPS
                if idx == len(steps) - 1:
                    expected_phase, expected_idx = "loop", 0
                else:
                    expected_phase, expected_idx = phase, idx + 1
                self.assertEqual(
                    (state["phase"], state["idx"]),
                    (expected_phase, expected_idx),
                    f"{phase}[{idx}] {label} 执行后状态未恰好推进一格",
                )
                switches = [c for c in stub.calls if c in ("fast_switch", "normal_switch")]
                self.assertEqual(
                    len(switches), 1,
                    f"{phase}[{idx}] {label} 应发起且只发起一次切人，实际 {switches}",
                )

    def test_attack_ending_steps_use_fast_swap(self):
        """以 A/下落A 收尾的节点必须走 fast-swap，其余走原生切人。"""
        for phase, idx, (char_name, label, actions) in _all_steps():
            with self.subTest(phase=phase, idx=idx, label=label):
                state = {"phase": phase, "idx": idx}
                stub = _make_stub(char_name, state)
                stub.yangqiansui_perform_step(state)
                expected = "fast_switch" if actions[-1] in ("a", "fall_a") else "normal_switch"
                self.assertIn(expected, stub.calls)

    def test_not_my_turn_only_switches(self):
        state = {"phase": "opener", "idx": 0}
        wrong = next(name for name in AXIS_TEAM if name != OPENER_STEPS[0][0])
        stub = _make_stub(wrong, state)
        stub.yangqiansui_perform_step(state)
        self.assertNotIn("click", stub.calls)
        self.assertNotIn("resonance", stub.calls)


class TestConditionalSuisuiE(unittest.TestCase):
    def _run(self, has_signature):
        stub = _make_stub("Suisui")
        stub.is_signature_weapon_config = lambda: has_signature
        stub._yangqiansui_execute_action("e_if_no_signature")
        return stub.calls

    def test_signature_weapon_skips_extra_e(self):
        self.assertNotIn("resonance", self._run(True))

    def test_no_signature_weapon_sends_extra_e(self):
        self.assertIn("resonance", self._run(False))


if __name__ == "__main__":
    unittest.main()
