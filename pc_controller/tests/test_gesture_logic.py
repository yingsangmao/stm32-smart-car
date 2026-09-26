"""手势决策逻辑的单元测试。

只测真正会出错的规则：稳定时间、手势切换、输入消失、输入过期、指令映射。
不需要摄像头、不需要串口、不需要 STM32，直接运行：

    python -m unittest discover -s pc_controller/tests -t .
  或
    cd pc_controller && python -m unittest discover -s tests -t .
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gesture_logic import (  # noqa: E402
    GestureDecider,
    Intent,
    GESTURE_TO_INTENT,
    normalize_gesture_name,
)


class TestGestureNameNormalization(unittest.TestCase):
    """回归测试：MediaPipe"认不出手势"时返回的是字符串 "None"。

    实测踩过：这个 "None" 被当成一个真实手势类别，进了统计和判定，
    置信度还能到 0.86，把 --min-score 的建议整个带偏。
    """

    def test_normalize_variants(self):
        self.assertIsNone(normalize_gesture_name(None))
        self.assertIsNone(normalize_gesture_name(""))
        self.assertIsNone(normalize_gesture_name("   "))
        self.assertIsNone(normalize_gesture_name("None"))
        self.assertIsNone(normalize_gesture_name("none"))

    def test_normalize_keeps_real_gestures(self):
        self.assertEqual(normalize_gesture_name("Closed_Fist"), "Closed_Fist")
        self.assertEqual(normalize_gesture_name(" Open_Palm "), "Open_Palm")

    def test_decider_treats_none_string_as_no_gesture(self):
        """即使调用方漏了归一化，决策层也必须挡住它。"""
        d = GestureDecider(hold_ms=200)
        for i in range(20):
            d.update("None", 0.99, now=i * 0.05)
        decision = d.poll(now=1.0)
        self.assertEqual(decision.intent, Intent.STOP)
        self.assertIsNone(decision.gesture)


class TestMapping(unittest.TestCase):
    """指令映射：握拳左转、张开手掌右转，数值必须和 STM32 端一致。"""

    def test_mapping_values(self):
        self.assertEqual(GESTURE_TO_INTENT["Closed_Fist"], Intent.LEFT)
        self.assertEqual(GESTURE_TO_INTENT["Open_Palm"], Intent.RIGHT)
        self.assertEqual(int(Intent.LEFT), 0x03)
        self.assertEqual(int(Intent.RIGHT), 0x04)
        self.assertEqual(int(Intent.STOP), 0x00)

    def test_decision_byte_is_raw(self):
        d = GestureDecider()
        d.update("Closed_Fist", 0.95, now=0.0)
        self.assertEqual(d.poll(now=0.25).byte, 3)
        self.assertEqual(d.poll(now=0.25).byte, int(Intent.LEFT))


class TestHoldTime(unittest.TestCase):
    """同一个手势必须稳定够久才允许转向；切换过程中必须停车。"""

    def test_stop_before_hold_expires(self):
        d = GestureDecider(hold_ms=200)
        d.update("Closed_Fist", 0.95, now=0.0)
        self.assertEqual(d.poll(now=0.100).intent, Intent.STOP)
        self.assertEqual(d.poll(now=0.199).intent, Intent.STOP)

    def test_turn_once_hold_reached(self):
        d = GestureDecider(hold_ms=200)
        d.update("Closed_Fist", 0.95, now=0.0)
        self.assertEqual(d.poll(now=0.200).intent, Intent.LEFT)

    def test_hold_uses_elapsed_time_not_frame_count(self):
        # 10ms 一帧（约 100fps）和 100ms 一帧（10fps），结果必须一样
        fast = GestureDecider(hold_ms=200)
        slow = GestureDecider(hold_ms=200)
        for i in range(30):
            fast.update("Open_Palm", 0.9, now=i * 0.010)
        for i in range(4):
            slow.update("Open_Palm", 0.9, now=i * 0.100)
        # 两边都在 0.35s 时刻判断：手势都已经持续远超 200ms
        self.assertEqual(fast.poll(now=0.35).intent, Intent.RIGHT)
        self.assertEqual(slow.poll(now=0.35).intent, Intent.RIGHT)

    def test_switch_back_to_stop_until_confirmed(self):
        """左转已生效后切到右转，未满稳定时间前必须是停车。"""
        d = GestureDecider(hold_ms=200)
        d.update("Closed_Fist", 0.95, now=0.0)
        self.assertEqual(d.poll(now=0.200).intent, Intent.LEFT)

        d.update("Open_Palm", 0.95, now=0.300)
        self.assertEqual(d.poll(now=0.400).intent, Intent.STOP)   # 还没稳定
        self.assertEqual(d.poll(now=0.499).intent, Intent.STOP)
        self.assertEqual(d.poll(now=0.500).intent, Intent.RIGHT)  # 稳定 200ms

    def test_long_hold_stays_turning(self):
        d = GestureDecider(hold_ms=200)
        d.update("Closed_Fist", 0.95, now=0.0)
        for t in (0.2, 0.4, 1.0, 5.0):
            d.update("Closed_Fist", 0.95, now=t - 0.01)
            self.assertEqual(d.poll(now=t).intent, Intent.LEFT)


class TestStopConditions(unittest.TestCase):
    """无手、低置信度、其他手势、多只手 —— 全部停车。"""

    def test_no_hand_stops(self):
        d = GestureDecider(hold_ms=200)
        d.update("Closed_Fist", 0.95, now=0.0)
        self.assertEqual(d.poll(now=0.200).intent, Intent.LEFT)
        d.update(None, 0.0, unknown_reason="画面中无手", now=0.300)
        self.assertEqual(d.poll(now=0.300).intent, Intent.STOP)
        self.assertIn("无手", d.poll(now=0.300).reason)

    def test_low_score_stops(self):
        d = GestureDecider(hold_ms=200, min_score=0.6)
        d.update("Closed_Fist", 0.95, now=0.0)
        self.assertEqual(d.poll(now=0.200).intent, Intent.LEFT)
        # 置信度掉到阈值以下，即使类别没变也必须停车
        d.update("Closed_Fist", 0.30, now=0.300)
        self.assertEqual(d.poll(now=0.500).intent, Intent.STOP)

    def test_unsupported_gesture_stops(self):
        d = GestureDecider(hold_ms=200)
        d.update("Closed_Fist", 0.95, now=0.0)
        self.assertEqual(d.poll(now=0.200).intent, Intent.LEFT)
        d.update("Victory", 0.99, now=0.300)
        self.assertEqual(d.poll(now=0.500).intent, Intent.STOP)
        self.assertIn("Victory", d.poll(now=0.500).reason)

    def test_multiple_hands_stops(self):
        d = GestureDecider(hold_ms=200)
        d.update("Closed_Fist", 0.95, now=0.0)
        self.assertEqual(d.poll(now=0.200).intent, Intent.LEFT)
        d.update(None, 0.0, unknown_reason="检测到 2 只手，意图有歧义", now=0.300)
        self.assertEqual(d.poll(now=0.500).intent, Intent.STOP)

    def test_first_frame_without_hand_does_not_crash(self):
        """回归测试：第一帧就没有手时，候选起始时刻必须被正确初始化。"""
        d = GestureDecider()
        decision = d.update(None, 0.0, unknown_reason="画面中无手", now=0.0)
        self.assertEqual(decision.intent, Intent.STOP)
        self.assertEqual(d.poll(now=0.050).intent, Intent.STOP)

    def test_alternating_gestures_never_turn(self):
        """来回切换永远凑不满稳定时间，必须一直停车。"""
        d = GestureDecider(hold_ms=200)
        for i in range(10):
            d.update("Closed_Fist" if i % 2 == 0 else "Open_Palm", 0.95,
                     now=i * 0.150)
            self.assertEqual(d.poll(now=i * 0.150).intent, Intent.STOP)


class TestStaleInput(unittest.TestCase):
    """识别流程停止更新时，旧的转向命令不能继续生效。"""

    def test_stale_input_stops(self):
        d = GestureDecider(hold_ms=200, stale_ms=300)
        d.update("Closed_Fist", 0.95, now=0.0)
        self.assertEqual(d.poll(now=0.200).intent, Intent.LEFT)
        # 之后再也没有新帧。300ms 容忍窗口内，仍按上一次结果执行
        self.assertEqual(d.poll(now=0.250).intent, Intent.LEFT)
        # 超过窗口：必须自己停下来，不能让旧命令一直生效
        decision = d.poll(now=0.350)
        self.assertEqual(decision.intent, Intent.STOP)
        self.assertIn("停止更新", decision.reason)

    def test_stale_then_recover_needs_full_hold_again(self):
        d = GestureDecider(hold_ms=200, stale_ms=300)
        d.update("Closed_Fist", 0.95, now=0.0)
        self.assertEqual(d.poll(now=0.200).intent, Intent.LEFT)
        self.assertEqual(d.poll(now=0.250).intent, Intent.LEFT)

        self.assertEqual(d.poll(now=1.000).intent, Intent.STOP)   # 过期停车

        # 恢复供帧后，必须重新稳定满 200ms 才允许再转向
        d.update("Closed_Fist", 0.95, now=1.100)
        self.assertEqual(d.poll(now=1.150).intent, Intent.STOP)
        self.assertEqual(d.poll(now=1.300).intent, Intent.LEFT)

    def test_no_frame_at_all_stops(self):
        d = GestureDecider()
        self.assertEqual(d.poll(now=10.0).intent, Intent.STOP)


class TestConfigurability(unittest.TestCase):
    """阈值可配置，且非法配置要尽早报错。"""

    def test_custom_min_score(self):
        d = GestureDecider(min_score=0.9)
        d.update("Closed_Fist", 0.85, now=0.0)
        d.update("Closed_Fist", 0.85, now=0.100)
        self.assertEqual(d.poll(now=0.100).intent, Intent.STOP)
        # 置信度升上来了，但要重新计时
        d.update("Closed_Fist", 0.95, now=0.200)
        self.assertEqual(d.poll(now=0.200).intent, Intent.STOP)
        d.update("Closed_Fist", 0.95, now=0.400)
        self.assertEqual(d.poll(now=0.400).intent, Intent.LEFT)

    def test_custom_hold_ms(self):
        d = GestureDecider(hold_ms=500)
        d.update("Closed_Fist", 0.95, now=0.0)
        d.update("Closed_Fist", 0.95, now=0.400)
        self.assertEqual(d.poll(now=0.400).intent, Intent.STOP)
        d.update("Closed_Fist", 0.95, now=0.500)
        self.assertEqual(d.poll(now=0.500).intent, Intent.LEFT)

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            GestureDecider(min_score=1.5)
        with self.assertRaises(ValueError):
            GestureDecider(hold_ms=-1)
        with self.assertRaises(ValueError):
            GestureDecider(stale_ms=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
