"""预览模式和实际控制模式共用的主循环。

gesture_preview.py 和 gesture_control.py 都是这个文件的薄包装：
区别只有一个——控制模式才会去 import pyserial、才会打开串口。
预览模式连 pyserial 都不加载，从根上杜绝"以为在预览结果把车开跑了"。
"""

import argparse
import csv
import os
import sys
import time

import cv2

import console
from display import (COLOR_BAD, COLOR_DIM, COLOR_LEFT, COLOR_OK, COLOR_RIGHT,
                     COLOR_STOP, COLOR_TEXT, TextRenderer, draw_hand_landmarks,
                     draw_panel)
from gesture_logic import GestureDecider, Intent, intent_text
from recognizer import GestureRecognizerWrapper

# 让中文控制台不会因为个别符号编码不出来而崩掉，见 console.py
console.setup()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL = os.path.join(SCRIPT_DIR, "models", "gesture_recognizer.task")

WINDOW = "STM32 gesture control  (q/ESC to quit)"

_BACKENDS = {
    "auto": None,
    "dshow": cv2.CAP_DSHOW,     # Windows 上打开最快，推荐
    "msmf": cv2.CAP_MSMF,
    "any": cv2.CAP_ANY,
}

_INTENT_COLOR = {
    Intent.STOP: COLOR_STOP,
    Intent.LEFT: COLOR_LEFT,
    Intent.RIGHT: COLOR_RIGHT,
}


def build_parser(enable_serial: bool) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="手势遥控" + ("（实际控制）" if enable_serial else "（仅预览，不连小车）"),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    p.add_argument("--camera", type=int, default=0,
                   help="摄像头编号，0 一般是默认摄像头；插了多个就试 1、2")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help="gesture_recognizer.task 模型路径")
    p.add_argument("--width", type=int, default=640, help="采集画面宽")
    p.add_argument("--height", type=int, default=480, help="采集画面高")
    p.add_argument("--backend", choices=sorted(_BACKENDS), default="auto",
                   help="OpenCV 采集后端，Windows 上 dshow 通常最快")
    p.add_argument("--no-mirror", action="store_true",
                   help="不左右镜像画面（默认镜像，符合照镜子的直觉）")

    g = p.add_argument_group("手势判定参数")
    g.add_argument("--hold-ms", type=float, default=200.0,
                   help="同一手势需持续多少毫秒才允许转向")
    g.add_argument("--min-score", type=float, default=0.60,
                   help="置信度阈值，低于它按无法确定处理（停车）")
    g.add_argument("--stale-ms", type=float, default=300.0,
                   help="多久没有新的识别结果就按输入过期处理（停车）")
    g.add_argument("--num-hands", type=int, default=2,
                   help="最多检测几只手；设为 2 是为了能发现'多只手有歧义'")

    p.add_argument("--log-scores", metavar="FILE", default=None,
                   help="把每帧的【原始】手势类别和置信度记到 CSV。"
                        "原始值不受 --min-score 影响，用来客观挑选阈值；"
                        "录完用 python analyze_scores.py FILE 看统计和建议值")

    if enable_serial:
        s = p.add_argument_group("串口参数")
        s.add_argument("--port", default="auto",
                       help="COM 口，例如 COM7；auto=自动挑唯一的蓝牙串口")
        s.add_argument("--baud", type=int, default=9600,
                       help="波特率，必须和 STM32 端一致")
        s.add_argument("--heartbeat-ms", type=int, default=100,
                       help="每隔多少毫秒重复发一次当前指令（STM32 靠它判断电脑还活着）")
        s.add_argument("--list-ports", action="store_true",
                       help="列出所有串口后退出")
    return p


# ----------------------------------------------------------------------
def open_camera(index: int, width: int, height: int, backend: str):
    """打开摄像头。auto 时先试 DSHOW，失败再试 MSMF。"""
    order = ["dshow", "msmf", "any"] if backend == "auto" else [backend]
    for name in order:
        cap = cv2.VideoCapture(index, _BACKENDS[name])
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                print("摄像头已打开：编号 %d，后端 %s" % (index, name))
                return cap
            cap.release()
    return None


def pick_port(requested: str, ports):
    """决定用哪个 COM 口。返回 (port, error_message)。"""
    if requested and requested.lower() != "auto":
        return requested, None

    # 只看"确实绑定了某个设备"的蓝牙口，排除电脑自身适配器那个通用的
    # 传入口 —— 后者永远连不上小车，选它只会白白浪费排查时间。
    bluetooth = [p for p in ports if p.is_usable_bluetooth]
    if len(bluetooth) == 1:
        print("自动选中蓝牙串口：%s（%s）"
              % (bluetooth[0].device, bluetooth[0].description))
        return bluetooth[0].device, None

    if not bluetooth:
        all_bt = [p for p in ports if p.looks_like_bluetooth]
        if all_bt:
            return None, (
                "只发现了电脑自身蓝牙适配器的通用口（%s），它连不上具体设备。\n"
                "请确认小车已通电、并且已经配对成功。"
                % ", ".join(p.device for p in all_bt))
        return None, ("没有发现蓝牙串口。请先配对，"
                      "配对成功后 Windows 才会创建对应的 COM 口。")

    return None, ("发现多个可用的蓝牙串口，请用 --port 指定一个："
                  + ", ".join(p.device for p in bluetooth))


def make_status_items(decision, link, fps, preview_mode: bool):
    """组装画面左上角的信息面板内容。"""
    # 第一行：原始手势类别 + 置信度
    if decision.gesture is None:
        gesture_line = "手势: 无"
    else:
        gesture_line = "手势: %s  置信度 %.2f" % (decision.gesture, decision.score)

    # 第二行：最终控制意图（最大最醒目）
    intent_line = "意图: %s  (0x%02X)" % (
        intent_text(decision.intent), decision.byte)

    # 第三行：判定理由
    reason_line = "判定: %s" % decision.reason

    # 第四行：通信状态
    if preview_mode:
        comm_line = "通信: 预览模式，未连接小车"
        comm_color = COLOR_DIM
    elif link is not None and link.connected:
        comm_line = "通信: %s" % link.status_text()
        comm_color = COLOR_OK
    else:
        comm_line = "通信: %s" % (link.status_text() if link else "未连接")
        comm_color = COLOR_BAD

    items = [
        (gesture_line, COLOR_TEXT, 20),
        (intent_line, _INTENT_COLOR[decision.intent], 34),
        (reason_line, COLOR_DIM, 18),
        (comm_line, comm_color, 18),
        ("FPS: %.1f" % fps, COLOR_DIM, 16),
    ]
    if not preview_mode:
        items.append(("按 q / ESC 退出；断开后按 r 重连串口", COLOR_DIM, 16))
    else:
        items.append(("按 q / ESC 退出", COLOR_DIM, 16))
    return items


# ----------------------------------------------------------------------
def main(argv, enable_serial: bool) -> int:
    args = build_parser(enable_serial).parse_args(argv)

    if not os.path.isfile(args.model):
        print("找不到模型文件：%s" % args.model)
        print("请先运行：python get_model.py")
        return 2

    link = None
    total_frames = 0

    if enable_serial:
        from serial_link import SerialLink, list_serial_ports, format_port_table

        ports = list_serial_ports()
        if args.list_ports:
            print("系统上的串口：")
            print(format_port_table(ports))
            return 0

        port, err = pick_port(args.port, ports)
        if port is None:
            print(err)
            print("\n当前串口列表：")
            print(format_port_table(ports))
            print("\n也可以直接用 USB 转 TTL 模块接 STM32 的 PA9/PA10 调试。")
            return 2

        link = SerialLink(port, baudrate=args.baud,
                          heartbeat_ms=args.heartbeat_ms)
        if not link.open():
            print("\n串口打不开。常见原因：")
            print("  - 这个 COM 口正被别的程序占用（串口助手、Keil 等）")
            print("  - 蓝牙还没连上（配对 ≠ 建链，见 README）")
            print("  - 口选错了，用 --list-ports 看一下")
            return 2

    cap = open_camera(args.camera, args.width, args.height, args.backend)
    if cap is None:
        print("打不开摄像头（编号 %d）。可以试试 --camera 1 或 --camera 2。" % args.camera)
        if link is not None:
            link.close()
        return 2

    print("加载模型：%s" % args.model)
    recognizer = GestureRecognizerWrapper(args.model, num_hands=args.num_hands)
    decider = GestureDecider(hold_ms=args.hold_ms,
                             min_score=args.min_score,
                             stale_ms=args.stale_ms)

    # 分数记录（可选）：记的是【原始】分类结果，不受 --min-score 影响，
    # 所以可以拿来反推阈值该定多少，而不是靠盯着屏幕猜。
    score_file = None
    score_writer = None
    if args.log_scores:
        is_new = not os.path.isfile(args.log_scores)
        score_file = open(args.log_scores, "a", newline="", encoding="utf-8")
        score_writer = csv.writer(score_file)
        if is_new:
            score_writer.writerow(["t_ms", "gesture", "score", "num_hands",
                                   "intent", "byte", "reason"])
        print("分数记录到：%s" % args.log_scores)

    if enable_serial:
        print("\n已进入手势遥控模式：小车现在处于停车状态，"
              "作出手势并稳定 %.0fms 后才会动。" % args.hold_ms)
    else:
        print("\n预览模式：不会向小车发送任何指令。")

    renderer = TextRenderer()
    if not renderer.cjk_supported:
        print("提示：没找到中文字体，画面上的中文会显示成问号（不影响功能）。")

    start = time.monotonic()
    last_draw = start
    fps = 0.0
    read_fail = 0
    mirror = not args.no_mirror
    exit_code = 0

    try:
        while True:
            ok, frame = cap.read()
            now = time.monotonic()

            if ok:
                read_fail = 0
                if mirror:
                    frame = cv2.flip(frame, 1)

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = recognizer.recognize(rgb, int((now - start) * 1000))

                # 关键：把这一帧喂给决策器，而不是直接把分类结果当命令
                decision = decider.update(result.gesture, result.score,
                                          result.note, now=now)
                raw = (result.gesture, result.score, result.num_hands)

                ambiguous = result.num_hands > 1
                highlight = 0 if (result.num_hands == 1 and result.gesture) else None
                draw_hand_landmarks(frame, result.hands,
                                    highlight_index=highlight, ambiguous=ambiguous)
            else:
                # 画面读不到：不喂新帧，让决策器走"输入过期"分支 → 停车
                read_fail += 1
                if read_fail == 30:
                    print("警告：连续 30 次读不到画面，已按输入过期处理（停车）。")
                decision = decider.poll(now=now)
                raw = None
                if frame is None:
                    frame = _no_signal_frame(args.width, args.height)

            if link is not None and link.connected:
                link.send_intent(decision.intent, now=now)

            if score_writer is not None:
                if raw is None:
                    score_writer.writerow(["%.0f" % ((now - start) * 1000),
                                           "", "", -1,
                                           intent_text(decision.intent),
                                           "0x%02X" % decision.byte,
                                           decision.reason])
                else:
                    score_writer.writerow(["%.0f" % ((now - start) * 1000),
                                           raw[0] or "", "%.4f" % raw[1], raw[2],
                                           intent_text(decision.intent),
                                           "0x%02X" % decision.byte,
                                           decision.reason])
                score_file.flush()

            span = now - last_draw
            if span > 0:
                fps = fps * 0.9 + (1.0 / span) * 0.1
            last_draw = now
            total_frames += 1

            draw_panel(frame, renderer,
                       make_status_items(decision, link, fps, link is None))
            cv2.imshow(WINDOW, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("r") and link is not None and not link.connected:
                print("尝试重新连接 %s ..." % link.port)
                if link.open():
                    decider = GestureDecider(hold_ms=args.hold_ms,
                                             min_score=args.min_score,
                                             stale_ms=args.stale_ms)
                    print("已重连，重新进入手势模式并停车。")

    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，准备退出。")
    finally:
        print("共处理 %d 帧。正在收尾..." % total_frames)
        cap.release()
        cv2.destroyAllWindows()
        recognizer.close()
        if link is not None:
            link.close()
        if score_file is not None:
            score_file.close()
            print("分数已保存。看统计和建议阈值：")
            print("  python analyze_scores.py %s" % args.log_scores)
    return exit_code


def _no_signal_frame(width: int, height: int):
    import numpy as np
    frame = np.zeros((height, width, 3), dtype="uint8")
    frame[:] = (25, 25, 25)
    return frame


if __name__ == "__main__":
    raise SystemExit("请运行 gesture_preview.py 或 gesture_control.py")
