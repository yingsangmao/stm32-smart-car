"""下载 MediaPipe 官方预训练手势模型 gesture_recognizer.task。

第一版不自建数据集、不训练模型，直接用官方 .task 文件。
默认下载 float16 版本（约 8MB，识别速度更快）。

用法：
    python get_model.py                 # 下载到 ./models/gesture_recognizer.task
    python get_model.py --force         # 已存在也重新下载
    python get_model.py --url <URL>     # 换一个地址
    python get_model.py --check         # 只检查本地文件是否可用
"""

import argparse
import hashlib
import os
import sys
import zipfile

import console

console.setup()

# 官方模型仓库（mediapipe-models 公共存储桶）
# float16/1 是版本化的固定地址，内容不会变；把 1 换成 latest 会跟随最新版。
DEFAULT_URL = (
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
    "gesture_recognizer/float16/1/gesture_recognizer.task"
)

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "models", "gesture_recognizer.task")

MIN_EXPECTED_BYTES = 1024 * 1024   # 正常约 8MB，小于 1MB 肯定是下错了


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_model(path: str) -> bool:
    """检查文件是不是一个可用的 .task 模型。

    .task 实际上是一个 zip 包，里面含 model.tflite 等文件。
    这里不去解析它，只确认"是个完整的 zip"，足以区分
    "真模型"和"下到的是错误页面/半截文件"。
    """
    if not os.path.isfile(path):
        print("找不到模型文件：%s" % path)
        return False

    size = os.path.getsize(path)
    if size < MIN_EXPECTED_BYTES:
        print("模型文件太小（%d 字节），很可能没下完或下错了。" % size)
        return False

    if not zipfile.is_zipfile(path):
        print("模型文件不是有效的 .task 包（zip 格式校验失败）。")
        print("通常说明下载到的是网页/错误信息而不是模型本体。")
        return False

    with zipfile.ZipFile(path) as z:
        names = z.namelist()

    print("模型文件正常：%s" % path)
    print("  大小   : %.2f MB" % (size / 1024 / 1024))
    print("  sha256 : %s" % sha256_of(path))
    print("  内含   : %s" % ", ".join(names))
    return True


def download(url: str, dest: str) -> bool:
    import urllib.request

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"

    print("正在下载：%s" % url)
    print("保存到  ：%s" % dest)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = done * 100.0 / total
                        sys.stdout.write("\r  %5.1f%%  %.1f/%.1f MB"
                                         % (pct, done / 1048576.0,
                                            total / 1048576.0))
                    else:
                        sys.stdout.write("\r  %.1f MB" % (done / 1048576.0))
                    sys.stdout.flush()
        print()
    except Exception as exc:                     # noqa: BLE001
        print("\n下载失败：%s" % exc)
        if os.path.exists(tmp):
            os.remove(tmp)
        return False

    os.replace(tmp, dest)
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="下载 MediaPipe 官方手势识别模型")
    parser.add_argument("--url", default=DEFAULT_URL,
                        help="模型下载地址")
    parser.add_argument("--out", default=DEFAULT_PATH,
                        help="保存路径")
    parser.add_argument("--force", action="store_true",
                        help="已存在也重新下载")
    parser.add_argument("--check", action="store_true",
                        help="只检查本地模型是否可用")
    args = parser.parse_args(argv)

    if args.check:
        return 0 if check_model(args.out) else 1

    if os.path.isfile(args.out) and not args.force:
        print("模型已存在，跳过下载。")
        return 0 if check_model(args.out) else 1

    if not download(args.url, args.out):
        return 1

    if not check_model(args.out):
        return 1
    print("\n完成。可以运行：python gesture_preview.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
