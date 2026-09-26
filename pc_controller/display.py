"""画面叠加显示：手部关键点、手势类别与置信度、控制意图、通信状态。

中文用 Pillow 渲染（Windows 自带微软雅黑，一定能找到）。
没有 Pillow 时退回 cv2.putText，此时中文会显示成问号，但程序仍能跑。
"""

import os
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from recognizer import HAND_CONNECTIONS, HandObservation

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",    # 黑体
    r"C:\Windows\Fonts\Deng.ttf",      # 等线
    r"C:\Windows\Fonts\simsun.ttc",    # 宋体
)

# 意图配色（BGR）
COLOR_STOP = (70, 70, 235)
COLOR_LEFT = (80, 200, 60)
COLOR_RIGHT = (240, 170, 0)
COLOR_TEXT = (245, 245, 245)
COLOR_DIM = (170, 170, 170)
COLOR_OK = (90, 220, 90)
COLOR_BAD = (80, 80, 235)


class TextRenderer:
    """带缓存的文字渲染器。"""

    def __init__(self):
        self._font_path: Optional[str] = None
        self._pil_ok = False
        self._cache = {}
        try:
            from PIL import Image, ImageDraw, ImageFont   # noqa: F401
            self._pil_ok = True
        except ImportError:
            return
        for path in _FONT_CANDIDATES:
            if os.path.isfile(path):
                self._font_path = path
                break

    @property
    def cjk_supported(self) -> bool:
        return self._pil_ok and self._font_path is not None

    # ------------------------------------------------------------------
    def _render(self, text: str, size: int, color: Tuple[int, int, int]):
        key = (text, size, color)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        from PIL import Image, ImageDraw, ImageFont

        font = ImageFont.truetype(self._font_path, size)
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        left, top, right, bottom = probe.textbbox((0, 0), text, font=font)
        w, h = max(right - left, 1), max(bottom - top, 1)

        canvas = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
        ImageDraw.Draw(canvas).text((1 - left, 1 - top), text, font=font,
                                    fill=(color[2], color[1], color[0], 255))
        bgra = np.array(canvas)                  # RGBA
        result = (bgra[:, :, :3].copy(), bgra[:, :, 3].copy())
        if len(self._cache) > 512:               # 防止长时间运行无限增长
            self._cache.clear()
        self._cache[key] = result
        return result

    # ------------------------------------------------------------------
    def draw(self, frame, text: str, org: Tuple[int, int],
             color: Tuple[int, int, int] = COLOR_TEXT, size: int = 20) -> None:
        """把文字画到 frame 上（原地修改）。"""
        if not text:
            return

        if not self.cjk_supported:
            cv2.putText(frame, text.encode("ascii", "replace").decode(),
                        (org[0], org[1] + size), cv2.FONT_HERSHEY_SIMPLEX,
                        size / 32.0, color, 1, cv2.LINE_AA)
            return

        rgb, alpha = self._render(text, size, color)
        h, w = alpha.shape
        x, y = org
        fh, fw = frame.shape[:2]

        # 超出画面就裁剪，不要让它去写 frame 之外的像素
        if x >= fw or y >= fh:
            return
        x0, y0 = max(x, 0), max(y, 0)
        sx, sy = x0 - x, y0 - y
        w = min(w - sx, fw - x0)
        h = min(h - sy, fh - y0)
        if w <= 0 or h <= 0:
            return

        sub_rgb = rgb[sy:sy + h, sx:sx + w].astype(np.float32)
        sub_a = (alpha[sy:sy + h, sx:sx + w].astype(np.float32) / 255.0)[:, :, None]
        roi = frame[y0:y0 + h, x0:x0 + w].astype(np.float32)
        frame[y0:y0 + h, x0:x0 + w] = (roi * (1.0 - sub_a) + sub_rgb * sub_a
                                       ).astype(np.uint8)

    def size(self, text: str, size: int) -> Tuple[int, int]:
        if not self.cjk_supported:
            return (int(len(text) * size * 0.55), size)
        _, alpha = self._render(text, size, COLOR_TEXT)
        return (alpha.shape[1], alpha.shape[0])


def draw_panel(frame, renderer: TextRenderer,
               items: Sequence[Tuple[str, Tuple[int, int, int], int]],
               origin: Tuple[int, int] = (10, 10),
               pad: int = 10, line_gap: int = 6) -> None:
    """画一个半透明背景的信息面板。

    items: [(文字, 颜色, 字号), ...]
    """
    widths, heights = [], []
    for text, _color, size in items:
        w, h = renderer.size(text, size)
        widths.append(w)
        heights.append(h + line_gap)

    box_w = max(widths) + pad * 2 if widths else pad * 2
    box_h = sum(heights) + pad * 2
    x, y = origin
    fh, fw = frame.shape[:2]
    box_w = min(box_w, fw - x - 2)
    box_h = min(box_h, fh - y - 2)

    if box_w > 0 and box_h > 0:
        roi = frame[y:y + box_h, x:x + box_w]
        roi[:] = (roi * 0.30).astype(np.uint8)   # 压暗，保证文字看得清

    cy = y + pad
    for (text, color, size), hh in zip(items, heights):
        renderer.draw(frame, text, (x + pad, cy), color, size)
        cy += hh


def draw_hand_landmarks(frame, hands: List[HandObservation],
                        highlight_index: Optional[int] = None,
                        ambiguous: bool = False) -> None:
    """画手部关键点和连线。

    highlight_index : 唯一那只"有效手"的下标
    ambiguous       : 是否因为多只手而判为有歧义（此时全部标红）
    """
    fh, fw = frame.shape[:2]

    for i, hand in enumerate(hands):
        if not hand.landmarks:
            continue
        if ambiguous:
            color = COLOR_BAD
        elif highlight_index is None or i == highlight_index:
            color = COLOR_OK
        else:
            color = COLOR_DIM

        pts = [(int(px * fw), int(py * fh)) for px, py in hand.landmarks]

        for a, b in HAND_CONNECTIONS:
            if a < len(pts) and b < len(pts):
                cv2.line(frame, pts[a], pts[b], color, 2, cv2.LINE_AA)
        for p in pts:
            cv2.circle(frame, p, 4, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, p, 4, color, 1, cv2.LINE_AA)
