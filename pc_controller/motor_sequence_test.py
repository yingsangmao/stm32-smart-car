"""自动跑一遍电机动作序列，人只需要在旁边看。

用途：不用一个键一个键按，就能一次性确认
  - 左右转的方向对不对
  - 停车是否正常
  - STM32 的 500ms 超时保护是否真的生效

注意：跑之前必须把车轮架空。

用法：
    python motor_sequence_test.py --port COM4            # 倒计时 10 秒后开始
    python motor_sequence_test.py --port COM4 --delay 20 # 给自己多点准备时间
"""

import argparse
import sys
import time

import console
from gesture_logic import CMD_GESTURE_ENTER, CMD_GESTURE_EXIT, Intent
from serial_link import SerialLink, format_port_table, list_serial_ports

console.setup()

# (显示名, 字节 或 None, 持续秒数, 备注)
# 字节为 None 表示"故意什么都不发"，用来测 STM32 的超时保护
SEQUENCE = [
    ("进入手势模式 + 停车心跳", CMD_GESTURE_ENTER, 0.2, "OLED 右上角应出现 GES"),
    ("停车", Intent.STOP, 2.0, "轮子静止"),
    ("左转", Intent.LEFT, 2.5, "看方向：是不是左轮反转、右轮正转"),
    ("停车", Intent.STOP, 1.5, "轮子静止"),
    ("右转", Intent.RIGHT, 2.5, "看方向：是不是左轮正转、右轮反转"),
    ("停车", Intent.STOP, 1.5, "轮子静止"),
    ("左转（然后故意断掉心跳）", Intent.LEFT, 2.0, "接下来会突然不发数据"),
    ("【超时测试】完全不发送", None, 3.0,
     "电机应在约 0.5 秒内自己停下，OLED 变 TMO"),
    ("恢复正常心跳（停车）", Intent.STOP, 1.5, "OLED 应回到 GES"),
    ("退出手势模式", CMD_GESTURE_EXIT, 0.3, "OLED 右上角应变空白"),
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="自动跑一遍电机动作序列（需要人看着）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--port", default="auto", help="COM 口，例如 COM4")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--delay", type=float, default=10.0,
                        help="开始前的准备倒计时（秒）")
    parser.add_argument("--heartbeat-ms", type=int, default=100)
    args = parser.parse_args(argv)

    port = args.port
    if port.lower() == "auto":
        ports = list_serial_ports()
        bt = [p for p in ports if p.looks_like_bluetooth]
        if len(bt) == 1:
            port = bt[0].device
        elif len(bt) > 1:
            print("有多个蓝牙串口，请用 --port 指定：",
                  ", ".join(p.device for p in bt))
            return 2
        else:
            print("没找到蓝牙串口：")
            print(format_port_table(ports))
            return 2

    print("=" * 62)
    print("自动动作序列 —— 请把车轮架空，然后盯着轮子看")
    print("=" * 62)
    print()
    print("即将执行的步骤：")
    for i, (name, _byte, secs, note) in enumerate(SEQUENCE, 1):
        print("  %2d. %-24s %4.1fs   %s" % (i, name, secs, note))
    print()

    for remaining in range(int(args.delay), 0, -1):
        sys.stdout.write("\r  倒计时 %2d 秒... 请看向小车" % remaining)
        sys.stdout.flush()
        time.sleep(1)
    print("\r  开始！" + " " * 30)

    link = SerialLink(port, baudrate=args.baud,
                      heartbeat_ms=args.heartbeat_ms)
    if not link.open():
        print("串口打开失败：%s" % link.last_error)
        return 2

    t0 = time.monotonic()
    try:
        for name, byte, secs, note in SEQUENCE:
            elapsed = time.monotonic() - t0
            print("[%6.2fs] %-24s %s" % (elapsed, name, note))

            if byte == CMD_GESTURE_ENTER:
                link._write(CMD_GESTURE_ENTER)      # noqa: SLF001
                time.sleep(secs)
                continue
            if byte == CMD_GESTURE_EXIT:
                link._write(CMD_GESTURE_EXIT)       # noqa: SLF001
                time.sleep(secs)
                continue

            end = time.monotonic() + secs
            while time.monotonic() < end:
                if byte is None:
                    # 超时测试：故意什么都不发
                    time.sleep(0.01)
                    continue
                link.send_intent(Intent(int(byte)))
                time.sleep(0.01)

        time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n被中断。")
    finally:
        print()
        print(
            "共发送 %d 字节。正在退出（应发停车 + 退出模式）..." % link.sent_count)
        link.close()

    print()
    print("=" * 62)
    print("请对照回答这三个问题：")
    print("  1. 左转/右转的方向对不对？")
    print("  2. 【超时测试】那一步，轮子是不是自己停了？OLED 是不是变 TMO？")
    print("  3. 退出手势模式后，OLED 右上角是不是变空白？")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
