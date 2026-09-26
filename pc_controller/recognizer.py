"""MediaPipe Gesture Recognizer 封装。

只做一件事：把一帧 RGB 图像变成"手部关键点 + 手势类别 + 置信度"。
不做任何稳定性判断、不做任何转向决策——那些在 gesture_logic.py 里。

关于 API 版本：
本项目实测 mediapipe 1.0.1，它已经**删除了 mp.solutions**，
所以网上大量教程里的 mp.solutions.hands / mp.solutions.drawing_utils
在这个版本上会直接报 AttributeError。这里统一用 mediapipe.tasks 下的
vision.GestureRecognizer，手部连线表也自己定义，不依赖任何可能被移除的常量。
"""

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from gesture_logic import normalize_gesture_name

# 手部 21 个关键点的标准连接关系（MediaPipe 官方定义）
# 自己写死是为了不依赖 mediapipe 的版本差异
HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),          # 拇指
    (0, 5), (5, 6), (6, 7), (7, 8),          # 食指
    (5, 9), (9, 10), (10, 11), (11, 12),     # 中指
    (9, 13), (13, 14), (14, 15), (15, 16),   # 无名指
    (13, 17), (17, 18), (18, 19), (19, 20),  # 小指
    (0, 17),                                 # 手掌根部
)

# 本版只认这两个手势，其余类别一律当"无法确定"
SUPPORTED_GESTURES = ("Closed_Fist", "Open_Palm")


@dataclass
class HandObservation:
    """一只手。"""

    gesture: Optional[str]      # 识别出的手势类别，可能是 None
    score: float                # 该类别置信度
    landmarks: List[tuple] = field(default_factory=list)  # [(x, y), ...] 归一化坐标


@dataclass
class FrameResult:
    """一帧的识别结果。"""

    hands: List[HandObservation]
    gesture: Optional[str]      # 给决策器用的手势（只有单手且识别出类别时才有值）
    score: float
    note: str                   # gesture 为 None 时说明原因，用于画面显示

    @property
    def num_hands(self) -> int:
        return len(self.hands)


def resolve_model_path(model_path: str) -> str:
    """把模型路径换成一个 mediapipe 能打开的路径。

    坑在这里：mediapipe 的 C++ 层是用「窄字符」路径去打开模型文件的，
    在 Windows 上不会做 UTF-8 -> UTF-16 的转换。
    所以路径里只要有一个中文字符，就会得到

        FileNotFoundError: Unable to open file at D:\\...\\gesture_recognizer.task

    即使文件明明存在。本项目所在的目录名就带中文，所以必须处理。

    做法：路径含非 ASCII 字符时，把模型复制到纯 ASCII 的临时目录再加载。
    复制只做一次（按内容长度判断是否已是最新），之后启动几乎没有开销。
    """
    absolute = os.path.abspath(model_path)

    if absolute.isascii():
        return absolute

    temp_root = tempfile.gettempdir()
    if not temp_root.isascii():
        # 用户名也可能是中文，兜一个一定存在的纯 ASCII 目录
        temp_root = r"C:\ProgramData"

    tag = hashlib.sha1(absolute.encode("utf-8")).hexdigest()[:12]
    dest_dir = os.path.join(temp_root, "stm32_gesture_model", tag)
    dest = os.path.join(dest_dir, os.path.basename(absolute))

    try:
        if (os.path.isfile(dest)
                and os.path.getsize(dest) == os.path.getsize(absolute)):
            print("模型路径含非 ASCII 字符，改用临时副本：%s" % dest)
            return dest

        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(absolute, dest)
    except OSError as exc:
        raise RuntimeError(
            "模型路径含非 ASCII 字符（%s），mediapipe 打不开，"
            "而复制到临时目录也失败了：%s\n"
            "解决办法：把整个项目移动到纯英文路径下再运行。"
            % (absolute, exc)) from exc

    print("模型路径含非 ASCII 字符，已复制到：%s" % dest)
    return dest


class GestureRecognizerWrapper:
    """对 mediapipe vision.GestureRecognizer 的薄封装。"""

    def __init__(self,
                 model_path: str,
                 num_hands: int = 2,
                 min_hand_detection_confidence: float = 0.5,
                 min_hand_presence_confidence: float = 0.5,
                 min_tracking_confidence: float = 0.5):
        model_path = resolve_model_path(model_path)
        options = vision.GestureRecognizerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=num_hands,
            min_hand_detection_confidence=min_hand_detection_confidence,
            min_hand_presence_confidence=min_hand_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._recognizer = vision.GestureRecognizer.create_from_options(options)
        self._last_ts = -1
        self.num_hands = num_hands

    # ------------------------------------------------------------------
    def recognize(self, rgb_frame, timestamp_ms: int) -> FrameResult:
        """识别一帧。

        rgb_frame : numpy 数组，RGB 顺序，形状 (H, W, 3)
        timestamp_ms : 毫秒时间戳，必须单调递增
        """
        # VIDEO 模式要求时间戳严格递增，同毫秒内的两帧会被拒绝
        if timestamp_ms <= self._last_ts:
            timestamp_ms = self._last_ts + 1
        self._last_ts = timestamp_ms

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self._recognizer.recognize_for_video(mp_image, timestamp_ms)

        hands = self._extract_hands(result)
        gesture, score, note = self._summarize(hands)
        return FrameResult(hands=hands, gesture=gesture, score=score, note=note)

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_hands(result) -> List[HandObservation]:
        hands: List[HandObservation] = []
        landmark_sets = result.hand_landmarks or []
        gesture_sets = result.gestures or []

        for i, landmarks in enumerate(landmark_sets):
            name, score = None, 0.0
            if i < len(gesture_sets) and gesture_sets[i]:
                top = gesture_sets[i][0]        # 已按置信度从高到低排序
                # 注意归一化：认不出手势时 category_name 是字符串 "None"
                name = normalize_gesture_name(top.category_name)
                score = float(top.score) if name is not None else 0.0
            hands.append(HandObservation(
                gesture=name,
                score=score,
                landmarks=[(lm.x, lm.y) for lm in landmarks],
            ))
        return hands

    @staticmethod
    def _summarize(hands: List[HandObservation]):
        """把多只手收敛成"给决策器的一个输入"。

        任何不唯一、不确定的情况都返回 gesture=None，让决策器去输出停车。
        """
        if not hands:
            return None, 0.0, "画面中无手"

        if len(hands) > 1:
            # 多只手可能给出互相矛盾的手势，直接判为有歧义
            names = "、".join(h.gesture or "未识别" for h in hands)
            return None, 0.0, "检测到 %d 只手（%s），意图有歧义" % (len(hands), names)

        hand = hands[0]
        if hand.gesture is None:
            return None, 0.0, "检测到手，但未能识别出有效手势"

        return hand.gesture, hand.score, ""

    # ------------------------------------------------------------------
    def close(self) -> None:
        try:
            self._recognizer.close()
        except Exception:                       # noqa: BLE001
            pass
