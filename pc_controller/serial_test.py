"""串口独立测试：不涉及摄像头和手势，先单独确认"电脑能不能控制小车"。

阶段 3 用它。按键就发一个原始字节，直接对照小车反应，
把"串口链路的问题"和"手势识别的问题"分开排查。

用法：
    python serial_test.py --list            # 只看有哪些串口
    python serial_test.py --port COM7       # 进入交互式测试
    python serial_test.py --port COM7 --baud 9600

进入后按单个键（不用回车）：
    0 停车   1 直行   2 后退   3 左转   4 右转   5 避障   6 循迹
    e 进入手势模式(0x10)    x 退出手势模式(0x11)
    h 开/关"心跳重发"      —— 用来验证 STM32 的 500ms 超时停车
    q 退出（会尽力先发停车和退出模式）

注意：第一次测试请把车轮架空再按 1/2/3/4/5/6。
"""

import argparse
import sys
import time

import console
from gesture_logic import CMD_GESTURE_ENTER, CMD_GESTURE_EXIT
from serial_link import SerialLink, format_port_table, list_serial_ports

console.setup()

try:
    import msvcrt
except ImportError:                 # 非 Windows 退回按行输入
    msvcrt = None

# 键 -> (显示名, 字节)
KEYMAP = {
    "0": ("停车", 0x00),
    "1": ("直行", 0x01),
    "2": ("后退", 0x02),
    "3": ("左转", 0x03),
    "4": ("右转", 0x04),
    "5": ("避障", 0x05),
    "6": ("循迹", 0x06),
    "e": ("进入手势模式", 0x10),
    "x": ("退出手势模式", 0x11),
}


def print_keymap() -> None:
    print("\n可用按键：")
    print("  0 停车    1 直行    2 后退    3 左转    4 右转")
    print("  5 避障    6 循迹")
    print("  e 进入手势模式(0x10)    x 退出手势模式(0x11)")
    print("  h 开关心跳重发          q 退出")
    print()


def read_key():
    """读一个按键，没有就返回 None。"""
    if msvcrt is not None:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            # 忽略方向键之类的双字节扫描码
            if ch in ("\x00", "\xe0"):
                msvcrt.getwch()
                return None
            return ch
        return None

    # 非 Windows：按行输入
    import select
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.readline().strip()[:1]
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="串口独立测试（先不接小车逻辑）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--port", default="auto",
                        help="COM 口，例如 COM7；auto=自动挑唯一的蓝牙串口")
    parser.add_argument("--baud", type=int, default=9600, help="波特率")
    parser.add_argument("--heartbeat-ms", type=int, default=100,
                        help="心跳重发间隔(ms)")
    parser.add_argument("--list", action="store_true", help="列出串口后退出")
    parser.add_argument("--yes", action="store_true",
                        help="跳过'车轮是否架空'的确认")
    args = parser.parse_args(argv)

    ports = list_serial_ports()
    if args.list:
        print("系统上的串口：")
        print(format_port_table(ports))
        return 0

    port = args.port
    if port.lower() == "auto":
        bt = [p for p in ports if p.looks_like_bluetooth]
        if len(bt) == 1:
            port = bt[0].device
            print("自动选中蓝牙串口：%s" % port)
        else:
            print("无法自动确定串口，请用 --port 指定。当前串口：")
            print(format_port_table(ports))
            return 2

    if not args.yes:
        print("\n注意：请先确认车轮已架空（或用东西垫起），再继续。")
        try:
            if input("车轮已架空？输入 y 继续：").strip().lower() != "y":
                print("已取消。")
                return 1
        except EOFError:
            pass

    link = SerialLink(port, baudrate=args.baud, heartbeat_ms=args.heartbeat_ms)
    if not link.open():
        print("\n打开失败。用 --list 看一下串口列表是否正常。")
        return 2

    print_keymap()
    print("注意：这里【不会】自动发 0x10，需要手动按 e 才会进入手势模式。\n")

    heartbeat = False
    last_cmd = 0x00
    last_beat = time.monotonic()

    try:
        while True:
            now = time.monotonic()

            if heartbeat and link.connected:
                if (now - last_beat) * 1000.0 >= args.heartbeat_ms:
                    link._write(last_cmd)      # noqa: SLF001 - 测试工具，直接发
                    last_beat = now
                    print("\r心跳中：重发 0x%02X" % last_cmd, end="", flush=True)

            key = read_key()
            if key is None:
                time.sleep(0.01)
                continue

            key = key.lower()
            if key == "q":
                break

            if key == "h":
                heartbeat = not heartbeat
                print("\n心跳重发：%s" % ("开" if heartbeat else "关"))
                if heartbeat:
                    last_beat = 0.0
                continue

            if key not in KEYMAP:
                continue

            name, byte = KEYMAP[key]
            if not link.connected:
                print("\n串口已断开，无法发送。请退出后重新运行。")
                continue

            if link._write(byte):              # noqa: SLF001
                # 0x10/0x11 是模式控制字节，不是有效的控制帧：
                # STM32 只把 0x00/0x03/0x04 当作"心跳"来刷新超时计时。
                # 所以不能把它们记成 last_cmd 拿去重发，否则按 h 之后
                # OLED 会一直显示 TMO（已超时），看起来像功能坏了。
                if byte not in (CMD_GESTURE_ENTER, CMD_GESTURE_EXIT):
                    last_cmd = byte
                print("\n发送 0x%02X  %s" % (byte, name))
    except KeyboardInterrupt:
        print("\n收到 Ctrl+C。")
    finally:
        link.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
