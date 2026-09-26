"""串口层测试：用假串口验证实际发出去的字节序列。

不需要真的插蓝牙模块，也就不受"这台电脑此刻有没有 COM 口"影响。
验证的是最容易出错、又最难靠肉眼看出来的东西：字节内容、发送顺序、
心跳间隔、出错后的状态。

必须有 pyserial 才能跑（car-gesture 环境里已装）：

    conda activate car-gesture
    python tests/test_serial_link.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import serial  # noqa: F401
    HAVE_PYSERIAL = True
except ImportError:
    HAVE_PYSERIAL = False

from gesture_logic import CMD_GESTURE_ENTER, CMD_GESTURE_EXIT, Intent  # noqa: E402

if HAVE_PYSERIAL:
    from serial_link import PortInfo  # noqa: E402


@unittest.skipUnless(HAVE_PYSERIAL, "需要 pyserial")
class TestPortClassification(unittest.TestCase):
    """区分"能用的蓝牙口"和"电脑自身适配器的通用传入口"。

    配对之后 Windows 会同时给出这两个口，描述文字完全一样、只有实例 ID
    不同。选错的那个不会报错，只是"打开成功但毫无反应"。

    下面的 hwid 是按真实结构构造的样例值 —— 真实设备的地址不适合
    写进公开仓库。
    """

    HWID_USABLE = (
        r"BTHENUM\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0002"
        r"\7&1A2B3C4D&0&001122AABBCC_C00000000")
    HWID_GENERIC = (
        r"BTHENUM\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000"
        r"\7&1A2B3C4D&0&000000000000_00000000")
    HWID_USB_SERIAL = r"USB\VID_1A86&PID_7523\6&6D75FD6&0&1"

    def test_bound_port_is_usable(self):
        p = PortInfo("COM4", "蓝牙链接上的标准串行 (COM4)", self.HWID_USABLE)
        self.assertTrue(p.looks_like_bluetooth)
        self.assertFalse(p.is_generic_incoming)
        self.assertTrue(p.is_usable_bluetooth)

    def test_generic_incoming_port_is_not_usable(self):
        p = PortInfo("COM5", "蓝牙链接上的标准串行 (COM5)", self.HWID_GENERIC)
        self.assertTrue(p.looks_like_bluetooth)
        self.assertTrue(p.is_generic_incoming)
        self.assertFalse(p.is_usable_bluetooth)
        self.assertIn("不要用", str(p))

    def test_usb_serial_is_not_bluetooth(self):
        p = PortInfo("COM3", "USB-SERIAL CH340 (COM3)", self.HWID_USB_SERIAL)
        self.assertFalse(p.looks_like_bluetooth)
        self.assertFalse(p.is_usable_bluetooth)
        self.assertNotIn("蓝牙", str(p))

    def test_auto_pick_skips_the_generic_port(self):
        """--port auto：两个口都在时，必须挑 COM4 而不是 COM5。"""
        try:
            import app
        except Exception as exc:            # noqa: BLE001
            self.skipTest("导入 app 需要 cv2/mediapipe：%s" % exc)

        ports = [
            PortInfo("COM4", "蓝牙链接上的标准串行 (COM4)", self.HWID_USABLE),
            PortInfo("COM5", "蓝牙链接上的标准串行 (COM5)", self.HWID_GENERIC),
            PortInfo("COM3", "USB-SERIAL CH340 (COM3)", self.HWID_USB_SERIAL),
        ]
        port, err = app.pick_port("auto", ports)
        self.assertIsNone(err)
        self.assertEqual(port, "COM4")

    def test_auto_pick_reports_when_only_generic_exists(self):
        try:
            import app
        except Exception as exc:            # noqa: BLE001
            self.skipTest("导入 app 需要 cv2/mediapipe：%s" % exc)

        ports = [PortInfo("COM5", "蓝牙链接上的标准串行 (COM5)",
                          self.HWID_GENERIC)]
        port, err = app.pick_port("auto", ports)
        self.assertIsNone(port)
        self.assertIn("连不上具体设备", err)

    def test_explicit_port_is_trusted(self):
        try:
            import app
        except Exception as exc:            # noqa: BLE001
            self.skipTest("导入 app 需要 cv2/mediapipe：%s" % exc)

        port, err = app.pick_port("COM9", [])
        self.assertEqual(port, "COM9")
        self.assertIsNone(err)


@unittest.skipUnless(HAVE_PYSERIAL, "需要 pyserial")
class TestSerialLinkBytes(unittest.TestCase):
    """核心断言：发的是原始字节，不是字符串 "0x03" 或字符 "3"。"""

    def setUp(self):
        import serial_link

        self.mod = serial_link
        self._original = serial_link.serial.Serial
        self.written = []
        self.serial_kwargs = {}

        written = self.written
        kwargs_box = self.serial_kwargs

        class FakeSerial:
            def __init__(self, **kwargs):
                kwargs_box.update(kwargs)
                self.closed = False

            def write(self, data):
                written.append(bytes(data))
                return len(data)

            def flush(self):
                pass

            def close(self):
                self.closed = True

        serial_link.serial.Serial = FakeSerial

    def tearDown(self):
        self.mod.serial.Serial = self._original

    def make(self, **kwargs):
        return self.mod.SerialLink("COM_TEST", log=lambda *a: None, **kwargs)

    def flat(self):
        return [b[0] for b in self.written]

    # ------------------------------------------------------------------
    def test_open_sends_enter_then_stop(self):
        """连接后必须先进入手势模式，并立刻停车，不能自己开始转向。"""
        link = self.make()
        self.assertTrue(link.open())
        self.assertEqual(self.flat(), [CMD_GESTURE_ENTER, int(Intent.STOP)])
        self.assertEqual(int(Intent.STOP), 0x00)

    def test_bytes_are_raw_not_text(self):
        link = self.make()
        link.open()
        self.written.clear()
        link.send_intent(Intent.LEFT, now=1.0, force=True)
        # 必须是单个字节 0x03，而不是 b"0x03"(4 字节) 或 b"3"(1 字节但值是 0x33)
        self.assertEqual(self.written, [b"\x03"])
        self.assertEqual(len(self.written[0]), 1)

    def test_all_intents_use_protocol_values(self):
        link = self.make()
        link.open()
        self.written.clear()
        for intent, expected in ((Intent.STOP, 0x00),
                                 (Intent.LEFT, 0x03),
                                 (Intent.RIGHT, 0x04)):
            link.send_intent(intent, now=1.0, force=True)
            self.assertEqual(self.flat()[-1], expected)

    def test_intent_change_sends_immediately(self):
        """意图变化时必须立刻发出，不能被心跳间隔挡在后面。"""
        link = self.make(heartbeat_ms=100)
        link.open()
        link._last_send_ts = 0.0
        link._last_intent = Intent.STOP
        self.written.clear()

        self.assertTrue(link.send_intent(Intent.LEFT, now=0.010))
        self.assertEqual(self.flat(), [0x03])

    def test_same_intent_repeats_at_heartbeat_interval(self):
        """意图不变时按心跳间隔重复发——STM32 靠它判断电脑还活着。"""
        link = self.make(heartbeat_ms=100)
        link.open()
        link._last_send_ts = 0.0
        link._last_intent = Intent.STOP
        self.written.clear()

        self.assertTrue(link.send_intent(Intent.LEFT, now=0.010))    # 变化，立刻发
        self.assertEqual(self.flat(), [0x03])
        self.written.clear()

        self.assertFalse(link.send_intent(Intent.LEFT, now=0.050))   # 距上次 40ms
        self.assertFalse(link.send_intent(Intent.LEFT, now=0.099))   # 89ms，还没到
        self.assertTrue(link.send_intent(Intent.LEFT, now=0.111))    # 101ms，发
        self.assertEqual(self.flat(), [0x03])

    def test_open_uses_configured_baudrate(self):
        link = self.make(baudrate=9600)
        link.open()
        self.assertEqual(self.serial_kwargs.get("baudrate"), 9600)
        self.assertEqual(self.serial_kwargs.get("port"), "COM_TEST")

    def test_close_sends_stop_then_exit(self):
        """正常退出时尽力发停车 + 退出手势模式，然后释放串口。"""
        link = self.make()
        link.open()
        self.written.clear()
        link.close()
        self.assertEqual(self.flat(), [int(Intent.STOP), CMD_GESTURE_EXIT])
        self.assertFalse(link.connected)


@unittest.skipUnless(HAVE_PYSERIAL, "需要 pyserial")
class TestSerialLinkFailure(unittest.TestCase):
    """蓝牙掉线、USB 拔掉之后的行为。"""

    def setUp(self):
        import serial_link

        self.mod = serial_link
        self._original = serial_link.serial.Serial

        class FlakySerial:
            """可以按需让 write 抛异常的假串口。"""

            def __init__(self, **kwargs):
                self.closed = False
                self.fail_next = False

            def write(self, data):
                if self.fail_next:
                    raise OSError("蓝牙链路已断开")
                return len(data)

            def flush(self):
                pass

            def close(self):
                self.closed = True

        serial_link.serial.Serial = FlakySerial

    def tearDown(self):
        self.mod.serial.Serial = self._original

    def test_write_error_enters_disconnected_state(self):
        link = self.mod.SerialLink("COM_TEST", log=lambda *a: None)
        self.assertTrue(link.open())
        self.assertTrue(link.connected)

        link._ser.fail_next = True
        self.assertFalse(link.send_intent(Intent.LEFT, now=1.0, force=True))

        # 关键：发送失败后必须变成断开状态，上层据此停止运动控制
        self.assertFalse(link.connected)
        self.assertIsNotNone(link.last_error)
        self.assertIn("已断开", link.status_text())

    def test_no_send_after_disconnect(self):
        link = self.mod.SerialLink("COM_TEST", log=lambda *a: None)
        link.open()
        link._ser.fail_next = True
        link.send_intent(Intent.LEFT, now=1.0, force=True)

        # 断开之后任何发送都不再产生动作
        self.assertFalse(link.send_intent(Intent.RIGHT, now=2.0, force=True))
        self.assertFalse(link.send_intent(Intent.STOP, now=3.0, force=True))

    def test_open_failure_is_reported_not_raised(self):
        """端口被占用/不存在时不能抛异常把程序打崩。"""
        def boom(**kwargs):
            raise OSError("拒绝访问，端口被占用")

        self.mod.serial.Serial = boom
        link = self.mod.SerialLink("COM_TEST", log=lambda *a: None)
        self.assertFalse(link.open())
        self.assertFalse(link.connected)
        self.assertIn("占用", link.last_error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
