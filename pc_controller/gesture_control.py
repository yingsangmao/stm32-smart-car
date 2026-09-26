"""实际控制模式：手势识别 + 串口发送，真正驱动小车。

阶段 5 联调用。启动后会先让 STM32 进入手势遥控模式并发送停车，
不会一上来就自己转向。

用法：
    python gesture_control.py --list-ports
    python gesture_control.py --port COM7
    python gesture_control.py --port COM7 --camera 1 --hold-ms 250
    python gesture_control.py --help
"""

import sys

from app import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], enable_serial=True))
