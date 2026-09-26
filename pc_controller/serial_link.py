"""串口通信层：枚举 COM 口、连接、按心跳发送指令、出错即断开。

设计上刻意把"发送"和"决策"分开：
本模块只负责把已经决定好的字节发出去，并按固定间隔重复发（心跳）。
STM32 端靠这个心跳判断电脑是否还活着。

发送失败（蓝牙掉线、USB 拔掉、端口被占用）时不会抛异常给上层，
而是把 connected 置为 False 并关闭端口。上层看到 connected=False
就停止一切运动控制；同时 STM32 端 500ms 收不到心跳也会自己停车。
两道保险互不依赖。
"""

import time
from dataclasses import dataclass
from typing import List, Optional

import serial
from serial.tools import list_ports

from gesture_logic import Intent, CMD_GESTURE_ENTER, CMD_GESTURE_EXIT


@dataclass
class PortInfo:
    device: str
    description: str
    hwid: str

    @property
    def looks_like_bluetooth(self) -> bool:
        """是否是蓝牙串口。

        JDY-31 在 Windows 上配对后会出现一个"传出"COM 口，
        hwid 里有 BTHENUM，描述通常是 "Standard Serial over Bluetooth link"。
        """
        blob = "%s %s" % (self.description, self.hwid)
        blob = blob.lower()
        return ("bthenum" in blob
                or "bluetooth" in blob
                or "蓝牙" in blob)

    @property
    def is_generic_incoming(self) -> bool:
        """是否是电脑自身蓝牙适配器那个通用的"传入"口。

        配对之后 Windows 往往会给出**两个**蓝牙串口，其中一个不是连到
        任何具体设备的：实例 ID 里是 LOCALMFG&0000、远端地址全是 0。
        它永远连不上小车 —— 选错了不会报错，只是"打开成功但毫无反应"。

        配对成功的那个，实例 ID 里是 LOCALMFG&0002、并带真实 MAC。
        """
        blob = (self.hwid or "").lower()
        if "localmfg&0000" in blob:
            return True
        # 远端地址全 0 的写法，例如 ...&0&000000000000_00000000
        return "000000000000_00000000" in blob

    @property
    def is_usable_bluetooth(self) -> bool:
        """既像蓝牙、又确实绑定了某个设备的口 —— 这才是能用的那个。"""
        return self.looks_like_bluetooth and not self.is_generic_incoming

    def __str__(self) -> str:
        if not self.looks_like_bluetooth:
            tag = ""
        elif self.is_generic_incoming:
            tag = " [蓝牙-通用口，连不上设备，不要用]"
        else:
            tag = " [蓝牙-可用]"
        return "%-8s %s%s" % (self.device, self.description, tag)


def list_serial_ports() -> List[PortInfo]:
    """列出当前系统上的所有串口。"""
    return [
        PortInfo(p.device, p.description or "", p.hwid or "")
        for p in sorted(list_ports.comports(), key=lambda x: x.device)
    ]


def format_port_table(ports: List[PortInfo]) -> str:
    if not ports:
        return "  （没有发现任何串口）"
    lines = []
    for p in ports:
        lines.append("  " + str(p))
        if p.hwid:
            lines.append("           %s" % p.hwid)
    return "\n".join(lines)


class SerialLink:
    """和 STM32 之间的一条串口链路。"""

    def __init__(self, port: str, baudrate: int = 9600,
                 heartbeat_ms: int = 100, log=print):
        self.port = port
        self.baudrate = baudrate
        self.heartbeat_ms = heartbeat_ms
        self.log = log

        self._ser: Optional[serial.Serial] = None
        self.connected = False
        self.last_error: Optional[str] = None
        self._last_send_ts = 0.0
        self._last_intent = Intent.STOP
        self.sent_count = 0

    # ------------------------------------------------------------------
    def open(self, enter_mode: bool = True) -> bool:
        """打开串口。

        enter_mode=True 时会先发 0x10 让 STM32 进入手势遥控模式，
        紧接着发一次停车（0x00）——上车就是停着的，不会自己开始转。
        """
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0,          # 只写不读，不阻塞
                write_timeout=1.0,  # 蓝牙卡住时不要无限等
            )
        except Exception as exc:            # noqa: BLE001 - 要的就是"任何异常都算失败"
            self.last_error = str(exc)
            self.connected = False
            self.log("串口打开失败：%s" % exc)
            return False

        self.connected = True
        self.last_error = None
        self.log("串口已打开：%s @ %d" % (self.port, self.baudrate))

        if enter_mode:
            if self._write(CMD_GESTURE_ENTER):
                self._last_intent = Intent.STOP
                self._write(int(Intent.STOP))
                self._last_send_ts = time.monotonic()
                self.log("已发送 0x10 进入手势模式，并发送 0x00 停车")
        return True

    # ------------------------------------------------------------------
    def send_intent(self, intent: Intent, now: Optional[float] = None,
                    force: bool = False) -> bool:
        """发送当前意图。返回本次是否真的发出了字节。

        两条规则：
        - 意图**和上次不同**时立刻发出去，不受心跳间隔限制，
          否则转向指令最坏要等一整个心跳周期才生效。
        - 意图没变时按心跳间隔重复发——STM32 就是靠"持续收到"判断电脑还活着，
          所以哪怕指令没变也必须不停发。
        """
        if not self.connected:
            return False

        now = time.monotonic() if now is None else now
        unchanged = (intent == self._last_intent)
        if (not force and unchanged
                and (now - self._last_send_ts) * 1000.0 < self.heartbeat_ms):
            return False

        if not self._write(int(intent)):
            return False

        self._last_send_ts = now
        self._last_intent = intent
        return True

    # ------------------------------------------------------------------
    def _write(self, byte: int) -> bool:
        """发送一个原始字节。失败即断开。"""
        if not self.connected or self._ser is None:
            return False
        try:
            self._ser.write(bytes([byte & 0xFF]))
            self._ser.flush()
            self.sent_count += 1
            return True
        except Exception as exc:            # noqa: BLE001
            self._disconnect(exc)
            return False

    def _disconnect(self, exc: Exception) -> None:
        self.last_error = str(exc)
        self.connected = False
        self.log("串口发送失败，已进入断开状态：%s" % exc)
        self.log("  上层会停止运动控制；STM32 端 500ms 收不到心跳也会自己停车。")
        try:
            if self._ser is not None:
                self._ser.close()
        except Exception:                   # noqa: BLE001
            pass
        self._ser = None

    # ------------------------------------------------------------------
    def close(self) -> None:
        """退出时的收尾：尽力停车、退出手势模式，然后释放串口。

        这里的每一步都单独 try —— 蓝牙已经掉线时不能因为发不出去
        就连端口都不关。
        """
        if self._ser is not None and self.connected:
            try:
                self._ser.write(bytes([int(Intent.STOP)]))
                self._ser.write(bytes([CMD_GESTURE_EXIT]))
                self._ser.flush()
                self.log("已发送 0x00 停车 + 0x11 退出手势模式")
            except Exception as exc:        # noqa: BLE001
                self.log("退出时发送停车失败（已尽力）：%s" % exc)
        try:
            if self._ser is not None:
                self._ser.close()
        except Exception:                   # noqa: BLE001
            pass
        self._ser = None
        self.connected = False
        self.log("串口已释放")

    def status_text(self) -> str:
        if self.connected:
            return "已连接 %s @%d" % (self.port, self.baudrate)
        if self.last_error:
            return "已断开（%s）" % self.last_error
        return "未连接"

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
