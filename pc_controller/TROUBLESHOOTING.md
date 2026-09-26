# 疑难排查

本项目的开发过程中实际踩到并解决的问题。按"现象 → 原因 → 处理"整理，
方便以后（包括自己）再碰到时不用重新查。

---

## 1. 模型加载报 `FileNotFoundError`，但文件明明存在

```
FileNotFoundError: Unable to open file at D:\某个\带中文的\路径\gesture_recognizer.task
```

**原因**：MediaPipe 的 C++ 层用**窄字符路径**打开模型文件，在 Windows 上
不做 UTF-8 → UTF-16 转换。路径里只要有一个非 ASCII 字符就会失败，
即使文件确实在那里。

**处理**：`recognizer.resolve_model_path()` 会在路径含非 ASCII 字符时，
自动把模型复制到 `%TEMP%\stm32_gesture_model\<hash>\` 再加载，对使用者透明。
也可以直接把整个项目放在纯英文路径下。

---

## 2. `AttributeError: module 'mediapipe' has no attribute 'solutions'`

**原因**：mediapipe 1.0.x **已经删除了 `mp.solutions`**。
网上大量教程（以及很多博客）用的是旧 API：

```python
mp.solutions.hands          # 1.0 里不存在
mp.solutions.drawing_utils  # 1.0 里不存在
```

**处理**：统一改用 `mediapipe.tasks` 下的 `vision.GestureRecognizer`。
手部 21 点连线表在 `recognizer.py` 里自己定义（`HAND_CONNECTIONS`），
不依赖任何可能被移除的常量。

---

## 3. 装完 mediapipe 后运行报奇怪的 cv2 错误

**原因**：`pip install mediapipe opencv-python` 会装出**两个都提供 `cv2`
包**的发行版 —— mediapipe 依赖 `opencv-contrib-python`，而显式指定的
`opencv-python` 又装了一份。两者互相覆盖 `cv2` 目录，导致运行期出现
难以定位的错误。

**处理**：只留 `opencv-contrib-python`：

```bash
pip uninstall -y opencv-python
pip install opencv-contrib-python
```

`check_env.py` 会用 `importlib.metadata.packages_distributions()` 检查这一点。

---

## 4. 统计里冒出一个叫 `None` 的"手势"，置信度还很高

**现象**：用 `--log-scores` 记录后，统计里出现一个类别名就是 `None` 的
"手势"，分数能到 0.86，把阈值建议整个带偏。

**原因**：MediaPipe 在"检测到了手、但认不出是什么手势"时，返回的
`category_name` 是**字符串 `"None"`**（4 个字符），不是 Python 的 `None`。
不归一化的话，它会被当成一个真实的手势类别。

**处理**：`gesture_logic.normalize_gesture_name()` 统一把 `"None"` / 空串
归一成 `None`。在 `recognizer.py` 和 `GestureDecider` 两处都调用 ——
决策层是安全性的最后一道关，不管调用方传什么写法都不该让它混过去。

---

## 5. 脚本在中文 Windows 终端里直接崩：`UnicodeEncodeError`

```
UnicodeEncodeError: 'gbk' codec can't encode character '\u2717'
```

**原因**：中文 Windows 的控制台代码页是 **936(GBK)**，`sys.stdout.encoding`
就是 `gbk`。脚本里只要 `print()` 出一个 GBK 编不出的字符，整个程序就挂。

| GBK 编不出 | GBK 编得出 |
| --- | --- |
| `✓`(U+2713) `✗`(U+2717) `⚠`(U+26A0) `•`(U+2022) | `√`(U+221A) `×`(U+00D7) `→`(U+2192) `△`(U+25B3) |

中文本身没问题（GBK 覆盖常用汉字），出事的只是这类装饰性符号。

**处理**：两件事都做。
1. 把越界字符换掉；
2. `console.py` 提供保险：`sys.stdout.reconfigure(errors="replace")`。
   注意**不要**改成 `encoding="utf-8"` —— 那会让中文变成乱码；
   保留控制台原本的编码、只把编不出的字符降级成 `?` 才是对的。

**自查方法**：把文件里所有 `>127` 的字符逐个试 `.encode('gbk')`。
查控制台代码页用 `ctypes.windll.kernel32.GetConsoleOutputCP()`。

---

## 6. 配对后出现两个蓝牙串口，选错的那个永远连不上

**现象**：设备管理器 / `list_ports` 里出现**两个**描述完全一样的
"蓝牙链接上的标准串行 (COMx)"，选其中一个打开成功但毫无反应。

**原因**：Windows 为每个配对的设备创建一个 SPP 口，另外还会有一个
**电脑自身蓝牙适配器的通用"传入"口**。后者不是连到任何具体设备的。

**判断规则**：看 `hwid`（实例 ID）里的远端地址部分。

| 实例 ID 特征 | 含义 | 能不能用 |
| --- | --- | --- |
| `..._LOCALMFG&0002\...&<真实MAC>_C00000000` | 绑定了具体设备 | **用这个** |
| `..._LOCALMFG&0000\...&000000000000_00000000` | 通用传入口，地址全 0 | 不要用 |

**处理**：`serial_link.PortInfo` 里的 `is_generic_incoming` /
`is_usable_bluetooth` 实现了这条规则，`app.pick_port("auto", ...)`
据此自动挑选，跳过通用口。`--list-ports` 也会直接标注 `[蓝牙-可用]` /
`[蓝牙-通用口，连不上设备，不要用]`。

---

## 7. "配对成功"不等于"链路已建立"

COM 口在设备列表里出现，只代表配对完成。真正的 RFCOMM 连接发生在
程序 `open()` 串口的那一刻（实测建链约需 1 秒）。所以：

- 列表里有 COM 口 ≠ 一定能连上；
- 连接失败时先确认小车**已通电**（JDY-31 的指示灯常亮 = 已连上，闪烁 = 未连接）。

---

## 8. 模型下载下来不是模型

**现象**：`get_model.py` 下回来的文件很小，或者加载时报格式错误。

**原因**：网络受限时可能拿到的是错误页面 / 重定向内容，而不是模型本体。

**处理**：`.task` 实际上是个 zip 包。`get_model.py` 会校验
"是不是完整 zip" + "大小是否合理"，能挡住这种情况。
想手工核对就比对 sha256。

---

## 9. 摄像头打不开，或者窗口全黑

**原因与处理**：

- **被别的程序占用**（会议软件、相机 App）。`cap.isOpened()` 在这种情况下
  仍会返回 `True`，但读出来是空帧 —— 所以 `open_camera()` 会真的
  `read()` 一帧来验证，而不只信 `isOpened()`。
- **后端选择**。Windows 上 OpenCV 默认走 MSMF，内置摄像头经常开得慢甚至卡住。
  本项目默认用 **DirectShow**（`cv2.CAP_DSHOW`），`--backend auto` 会依次
  尝试 dshow → msmf → any。
- **编号选错**。内置摄像头一般是 `--camera 0`，外接的试 1、2。
  用 `check_env.py --cameras` 自动探测。

---

## 10. 自己写 `.bat` 启动器时踩的两个坑

如果要在 Windows 上做一个双击运行的启动器：

1. **换行必须是 CRLF**。批处理文件用 LF 换行会让 `cmd` 逐行解析错乱，
   报出一堆"不是内部或外部命令"。
2. **内容必须是 ASCII**。`.bat` 是 `cmd` 按当前代码页（中文系统是 GBK）
   逐字节读的，UTF-8 的中文会变乱码并**破坏命令本身**。
   要在启动器里显示中文，让被调用的 Python 程序去打印。

另外 `cmd.exe /c chcp` 在 Git Bash 里可能开成交互式 cmd 而卡住，
要查代码页用 `ctypes.windll.kernel32.GetConsoleOutputCP()` 更稳。
