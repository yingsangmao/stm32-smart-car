"""Windows 中文控制台的编码保险。

Windows 中文系统的控制台代码页是 936(GBK)，`sys.stdout.encoding` 就是 `gbk`。
脚本里只要出现一个 GBK 编不出的字符（比如 ✓ ✗ ⚠ 这类符号），`print`
就会抛 `UnicodeEncodeError` 把整个程序打断：

    UnicodeEncodeError: 'gbk' codec can't encode character '\\u2717'

这里**不**把输出改成 UTF-8 —— 那样中文会在 GBK 控制台里变成乱码。
而是保留控制台原本的编码，只把"编不出来的字符"降级成 `?`：
中文照常显示，个别符号变成问号，程序不会崩。

用法：入口脚本里

    import console
    console.setup()
"""

import sys


def setup() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            # 输出被重定向到不支持 reconfigure 的对象（比如某些 IDE 的
            # 捕获流）时跳过即可，不影响功能。
            pass
