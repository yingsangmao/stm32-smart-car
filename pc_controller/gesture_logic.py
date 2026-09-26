"""手势决策逻辑：把逐帧的手势分类结果，变成"可以执行的转向意图"。

这一层刻意不依赖 OpenCV / MediaPipe / pyserial，方便单独测试。
真正的规则有两类：

1. 一帧分类结果不能直接变成转向命令，必须"同一个有效手势持续稳定一段时间"。
   稳定性用**经过的毫秒数**判断（time.monotonic），不看帧数，
   所以摄像头帧率高低、偶尔掉帧都不会改变判定结果。

2. 任何不确定的情况一律停车：
   画面里没有手、置信度不够、是别的手势、同时出现多只手、
   手势刚切换还没稳定、以及**识别流程/摄像头停止更新**。

第 2 条里的最后一种情况最容易被忽略：摄像头拔掉或者识别线程卡死时，
"没有新结果"和"画面里没有手"看起来一样。本模块用 last_frame_ts
把两者区分开——但它们都输出停车，区别只体现在给用户看的原因文字上。
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class Intent(IntEnum):
    """控制意图。数值就是发给 STM32 的原始字节，不额外做映射。"""

    STOP = 0x00
    LEFT = 0x03
    RIGHT = 0x04


# 手势类别 -> 控制意图。只支持这两种，其余手势一律停车。
#
# 与工程原有协议保持完全一致：0x03 = 左转、0x04 = 右转。
# 注意：STM32 端 0x03/0x04 与实车实际转向的对应关系取决于电机接线，
# 若实车方向相反，应优先检查接线，而不是在这里写补偿。
GESTURE_TO_INTENT = {
    "Closed_Fist": Intent.LEFT,   # 握拳 -> 左转
    "Open_Palm": Intent.RIGHT,    # 张开手掌 -> 右转
}


# 毫秒比较的容差。用浮点秒数算出来的毫秒值会和整数阈值差一点点
# （例如 (1.3-1.1)*1000 == 199.99999999999997），加上这个容差后
# "刚好到达稳定时间"才会稳定地判定为已达到，而不是看浮点运气。
_EPS_MS = 1e-6


# 进入 STM32 手势模式 / 退出手势模式（与原有 0x00~0x06 不冲突）
CMD_GESTURE_ENTER = 0x10
CMD_GESTURE_EXIT = 0x11


def intent_text(intent: Intent) -> str:
    """给画面/控制台用的中文说法。"""
    return {
        Intent.STOP: "停车",
        Intent.LEFT: "左转",
        Intent.RIGHT: "右转",
    }[intent]


# 本项目的识别结果里，哪些名字算"其实没有手势"。
#
# 坑：MediaPipe 在"检测到了手、但认不出是什么手势"时，返回的类别名是
# **字符串 "None"**，不是 Python 的 None。如果不归一化，它会被当成一个
# 真实的手势类别参与判定和统计（实测确实发生过：统计里多出一个
# 叫 None 的"手势"，置信度还能到 0.86，把阈值建议整个带偏）。
def normalize_gesture_name(name):
    """把"没有手势"的各种写法统一成 None。"""
    if name is None:
        return None
    text = name.strip()
    if not text or text.lower() == "none":
        return None
    return text


@dataclass
class Decision:
    """一次决策结果，画面显示和串口发送都用它。"""

    intent: Intent
    reason: str            # 为什么是这个结果（给用户看）
    stable_ms: float       # 当前候选手势已经稳定了多久
    gesture: Optional[str]  # 本帧原始类别（可能是 None 或不受支持的类别）
    score: float           # 本帧原始置信度

    @property
    def byte(self) -> int:
        """要发给 STM32 的原始字节。"""
        return int(self.intent)


class GestureDecider:
    """把一个一个的手势分类结果，收敛成稳定的控制意图。

    参数
    ----
    hold_ms : float
        同一有效手势需要持续多久（毫秒）才允许转向。默认 200ms。
    min_score : float
        置信度阈值，低于它按"无法确定"处理，停车。默认 0.60。
    stale_ms : float
        多久（毫秒）没有拿到新的识别结果，就认为识别流程已经停住，停车。
        默认 300ms，比正常的帧间隔宽松，避免正常掉帧被误判。
    """

    def __init__(self, hold_ms: float = 200.0, min_score: float = 0.60,
                 stale_ms: float = 300.0):
        if hold_ms < 0:
            raise ValueError("hold_ms 不能为负数")
        if not 0.0 <= min_score <= 1.0:
            raise ValueError("min_score 必须在 0~1 之间")
        if stale_ms <= 0:
            raise ValueError("stale_ms 必须为正数")
        self.hold_ms = float(hold_ms)
        self.min_score = float(min_score)
        self.stale_ms = float(stale_ms)

        self._candidate: Optional[str] = None
        self._candidate_since: Optional[float] = None
        self._gesture: Optional[str] = None
        self._score: float = 0.0
        self._note: str = "等待第一帧"
        self._last_frame_ts: Optional[float] = None

    # ------------------------------------------------------------------
    # 外部输入
    # ------------------------------------------------------------------
    def update(self, gesture: Optional[str], score: float,
               unknown_reason: Optional[str] = None,
               now: Optional[float] = None) -> Decision:
        """喂进一帧识别结果。

        参数
        ----
        gesture : str | None
            本帧的原始手势类别。None 表示"这一帧没有可用手势"。
        score : float
            该类别对应的置信度。
        unknown_reason : str | None
            当 gesture 为 None 时，说明原因（"画面中无手" / "检测到多只手" ...），
            只用于显示，不影响决策——它们的结果都是停车。
        now : float | None
            当前时刻（秒）。默认取 time.monotonic()，测试时可注入。
        """
        now = _now(now)
        self._last_frame_ts = now
        # 这里再归一化一次是刻意的双保险：决策层是安全性的最后一道关，
        # 不管调用方传进来什么写法，都不该让 "None" 混成一个有效手势。
        self._gesture = normalize_gesture_name(gesture)
        self._score = float(score)
        self._note = unknown_reason or ""
        return self._decide(now)

    def poll(self, now: Optional[float] = None) -> Decision:
        """没有新帧时也应当周期性调用。

        摄像头掉线或识别流程卡住时不会有新帧进来，只有靠这里才能
        发现"输入已经过期"，从而停车。
        """
        return self._decide(_now(now))

    # ------------------------------------------------------------------
    # 决策
    # ------------------------------------------------------------------
    def _decide(self, now: float) -> Decision:
        if self._last_frame_ts is None:
            return self._result(Intent.STOP, "尚未开始识别", 0.0, now)

        gap_ms = (now - self._last_frame_ts) * 1000.0
        if gap_ms > self.stale_ms + _EPS_MS:
            # 关键：识别流程停住了，必须停车，绝不能让上一条转向命令继续生效
            self._reset_candidate(now)
            return self._result(
                Intent.STOP,
                "识别/摄像头停止更新（已 %.0fms 无新帧）" % gap_ms,
                0.0, now)

        candidate = self._candidate_gesture()
        # 注意 _candidate_since 也要判 None：如果第一帧就没有有效手势，
        # candidate(None) 和初始的 _candidate(None) 相等，光比 candidate 会漏掉初始化
        if candidate != self._candidate or self._candidate_since is None:
            # 切换了（包括变成"没有候选"），重新计时，这段时间内一律停车
            self._candidate = candidate
            self._candidate_since = now

        held_ms = (now - self._candidate_since) * 1000.0

        if candidate is None:
            return self._result(Intent.STOP, self._none_reason(), 0.0, now)

        if held_ms + _EPS_MS < self.hold_ms:
            return self._result(
                Intent.STOP,
                "%s 稳定中 %.0f/%.0fms" % (candidate, held_ms, self.hold_ms),
                held_ms, now)

        return self._result(
            GESTURE_TO_INTENT[candidate],
            "%s 已稳定 %.0fms" % (candidate, held_ms),
            held_ms, now)

    def _candidate_gesture(self) -> Optional[str]:
        """本帧是否构成一个"有效手势候选"。

        只有"类别是我们支持的"且"置信度够"才算候选。其余一律 None。
        """
        if self._gesture is None:
            return None
        if self._gesture not in GESTURE_TO_INTENT:
            return None
        if self._score < self.min_score:
            return None
        return self._gesture

    def _none_reason(self) -> str:
        if self._gesture is None:
            return self._note or "无法确定手势"
        if self._gesture not in GESTURE_TO_INTENT:
            return "不支持的手势 %s（本版只认握拳/张开手掌）" % self._gesture
        if self._score < self.min_score:
            return "%s 置信度不足 %.2f < %.2f" % (
                self._gesture, self._score, self.min_score)
        return "无法确定手势"

    def _reset_candidate(self, now: float) -> None:
        self._candidate = None
        self._candidate_since = now

    def _result(self, intent: Intent, reason: str,
                stable_ms: float, now: float) -> Decision:
        return Decision(
            intent=intent,
            reason=reason,
            stable_ms=stable_ms,
            gesture=self._gesture,
            score=self._score,
        )


def _now(now: Optional[float]) -> float:
    if now is not None:
        return float(now)
    import time
    return time.monotonic()
