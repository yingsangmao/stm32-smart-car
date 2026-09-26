"""预览模式：只用摄像头做手势识别，【不会】连接小车、不会发任何串口数据。

阶段 1、2 用它验证：摄像头画面、手部关键点、手势类别与置信度、
最终控制意图（左转/右转/停车）、以及稳定判断和无手停车是否符合预期。

用法：
    python gesture_preview.py
    python gesture_preview.py --camera 1 --hold-ms 300 --min-score 0.7
    python gesture_preview.py --help
"""

import sys

from app import main

if __name__ == "__main__":
    # enable_serial=False：这个入口连 pyserial 都不会去 import
    raise SystemExit(main(sys.argv[1:], enable_serial=False))
