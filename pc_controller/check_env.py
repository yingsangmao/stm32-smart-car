"""环境自检：一次性确认电脑这边所有依赖是否就绪。

在跑手势识别之前先运行它，能省掉大部分"跑不起来不知道哪错了"的时间。

用法：
    python check_env.py              # 检查依赖、模型、串口
    python check_env.py --cameras    # 额外逐个打开摄像头试探（摄像头灯会亮一下）
"""

import argparse
import importlib.metadata as md
import os
import sys

import console

console.setup()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, "models", "gesture_recognizer.task")


def check_python() -> bool:
    print("=" * 62)
    print("Python")
    print("=" * 62)
    print("  版本   : %s" % sys.version.replace("\n", " "))
    print("  解释器 : %s" % sys.executable)

    ok = sys.version_info >= (3, 9)
    if not ok:
        print("  × 版本过低，mediapipe 需要 Python 3.9 及以上")
    if "car-gesture" not in sys.executable:
        print("  ! 提醒：当前不是 car-gesture 环境。"
              "请先执行 conda activate car-gesture")
    return ok


def check_packages() -> bool:
    print()
    print("=" * 62)
    print("依赖包")
    print("=" * 62)

    required = {
        "mediapipe": "手势识别",
        "cv2": "OpenCV 摄像头画面",
        "serial": "pyserial 串口",
        "numpy": "数值计算",
        "PIL": "Pillow 中文文字叠加",
    }

    all_ok = True
    for module, purpose in required.items():
        try:
            mod = __import__(module)
            version = getattr(mod, "__version__", None)
            if version is None:
                version = _dist_version(module)
            print("  √ %-12s %-22s (%s)" % (module, version, purpose))
        except ImportError as exc:
            all_ok = False
            optional = module == "PIL"
            mark = "!" if optional else "×"
            print("  %s %-12s %-22s (%s)  %s" % (
                mark, module, "未安装", purpose,
                "可选，仅影响中文显示" if optional else str(exc)))

    # 顺手查一个很容易踩的坑：同时装了 opencv-python 和 opencv-contrib-python
    providers = md.packages_distributions().get("cv2", [])
    if len(providers) > 1:
        all_ok = False
        print()
        print("  × 发现多个包同时提供 cv2：%s" % ", ".join(providers))
        print("    它们会互相覆盖，必须只留一个。修复：")
        print("      pip uninstall -y opencv-python opencv-contrib-python")
        print("      pip install opencv-contrib-python")
    return all_ok


def check_model() -> bool:
    print()
    print("=" * 62)
    print("模型文件")
    print("=" * 62)

    if not os.path.isfile(MODEL_PATH):
        print("  × 找不到 %s" % MODEL_PATH)
        print("    运行 python get_model.py 下载")
        return False

    sys.path.insert(0, SCRIPT_DIR)
    from get_model import check_model as verify, sha256_of
    if not verify(MODEL_PATH):
        return False
    return True


def check_cameras() -> None:
    print()
    print("=" * 62)
    print("摄像头探测（摄像头指示灯会亮一下）")
    print("=" * 62)

    try:
        import cv2
    except ImportError:
        print("  cv2 没装，跳过")
        return

    found = []
    for index in range(3):
        cap = None
        try:
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if cap.isOpened():
                ok, frame = cap.read()
                if ok and frame is not None:
                    h, w = frame.shape[:2]
                    print("  √ --camera %d 可用，当前分辨率 %dx%d" % (index, w, h))
                    found.append(index)
                else:
                    print("  ! --camera %d 打开成功但读不到画面" % index)
        except Exception as exc:            # noqa: BLE001
            print("  ! --camera %d 异常：%s" % (index, exc))
        finally:
            if cap is not None:
                cap.release()

    if not found:
        print("  × 没有可用的摄像头编号")
        print("    - 确认摄像头没被其它程序（会议软件、相机 App）占用")
        print("    - 笔记本内置摄像头一般是 0，外接的可能要试 1 / 2")


def check_ports() -> None:
    print()
    print("=" * 62)
    print("串口")
    print("=" * 62)

    try:
        from serial_link import format_port_table, list_serial_ports
    except ImportError:
        print("  pyserial 没装，跳过")
        return

    ports = list_serial_ports()
    print(format_port_table(ports))
    if not any(p.looks_like_bluetooth for p in ports):
        print()
        print("  ! 没看到蓝牙串口。JDY-31 需要在 Windows 里配对之后，")
        print("    系统才会创建对应的 COM 口。配对步骤见 README。")


def _dist_version(module: str):
    for dist in md.packages_distributions().get(module, []):
        try:
            return md.version(dist)
        except md.PackageNotFoundError:
            continue
    return "未知版本"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="手势控制环境自检")
    parser.add_argument("--cameras", action="store_true",
                        help="逐个打开摄像头试探")
    args = parser.parse_args(argv)

    ok = check_python()
    ok = check_packages() and ok
    ok = check_model() and ok
    if args.cameras:
        check_cameras()
    check_ports()

    print()
    print("=" * 62)
    if ok:
        print("结论：电脑端依赖齐全。")
        print("  下一步：python gesture_preview.py    （预览，不连小车）")
    else:
        print("结论：有项目没通过，请按上面的提示处理后重新运行本脚本。")
    print("=" * 62)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
