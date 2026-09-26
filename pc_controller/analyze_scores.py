"""分析 --log-scores 记录的分数，给出 --min-score 的建议值。

用法：
    python analyze_scores.py scores.csv

怎么录才有意义：

    python gesture_preview.py --log-scores scores.csv

    然后按顺序做，每段之间把手移开画面停一下：
      1. 手完全不进画面         约 5 秒
      2. 握拳，保持不动         约 10 秒
      3. 张开手掌，保持不动     约 10 秒
      4. 随便做点别的手势（V 字、竖大拇指）  约 5 秒
    按 q 退出，然后跑本脚本。

脚本会统计每个手势类别的置信度分布，并给出一个
"既不太容易漏判、又不容易误触发"的阈值。
"""

import argparse
import csv
import math
import os
import sys
from collections import defaultdict

import console
from gesture_logic import normalize_gesture_name

console.setup()

SUPPORTED = ("Closed_Fist", "Open_Palm")


def percentile(sorted_values, fraction):
    """线性插值分位数。不依赖 numpy。"""
    n = len(sorted_values)
    if n == 0:
        return None
    if n == 1:
        return sorted_values[0]
    position = (n - 1) * fraction
    low = int(math.floor(position))
    high = min(low + 1, n - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (
        position - low)


def load(path):
    if not os.path.isfile(path):
        raise SystemExit("找不到文件：%s" % path)

    by_gesture = defaultdict(list)   # 手势名 -> [置信度]
    stats = {"total": 0, "no_hand": 0, "stalled": 0,
             "hand_no_gesture": 0, "multi_hand": 0}
    tracks = defaultdict(list)       # 手势名 -> [(t_ms, score)]

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            stats["total"] += 1
            try:
                num_hands = int(row.get("num_hands") or 0)
            except ValueError:
                num_hands = 0

            if num_hands < 0:
                stats["stalled"] += 1
                continue

            # 老记录里可能残留字符串 "None"，这里统一归一化
            gesture = normalize_gesture_name(row.get("gesture"))
            if gesture:
                try:
                    score = float(row["score"])
                except (KeyError, ValueError, TypeError):
                    continue
                by_gesture[gesture].append(score)
                tracks[gesture].append((float(row["t_ms"]), score))
            elif num_hands == 0:
                stats["no_hand"] += 1
            elif num_hands == 1:
                # 手在画面里，但模型没给出任何有效手势（或判为 None）
                stats["hand_no_gesture"] += 1
            else:
                stats["multi_hand"] += 1

    return by_gesture, stats, tracks


def longest_runs(tracks, gap_ms=400.0):
    """每个手势的最长连续时长（毫秒）。

    中间断开超过 gap_ms 就算新的一段。用来判断 --hold-ms 设多少合适：
    若实际能稳定保持 1 秒，200ms 的判定时间就很安全。
    """
    result = {}
    for gesture, points in tracks.items():
        best = 0.0
        start = prev = None
        for t, _score in sorted(points):
            if prev is None or t - prev > gap_ms:
                start = t
            prev = t
            best = max(best, t - start)
        result[gesture] = best
    return result


def report(by_gesture, stats, tracks):
    print("=" * 66)
    print("采样概况")
    print("=" * 66)
    print("  总帧数              : %d" % stats["total"])
    print("  画面中无手          : %d" % stats["no_hand"])
    print("  有手但认不出手势    : %d" % stats["hand_no_gesture"])
    print("  检测到多只手(有歧义): %d" % stats["multi_hand"])
    print("  无新帧(摄像头卡住)  : %d" % stats["stalled"])
    for g in SUPPORTED:
        print("  %-19s: %d 帧" % (g, len(by_gesture.get(g, []))))
    if stats["hand_no_gesture"] > stats["total"] * 0.3:
        print()
        print("  ! 有相当比例的帧属于「手在画面里但认不出手势」。")
        print("    常见原因：手离摄像头太远/太近、光线太暗、手背对着镜头、")
        print("    手指半握不握。这些帧都会被判为停车，属于安全但不好用的状态。")

    if not any(by_gesture.get(g) for g in SUPPORTED):
        print()
        print("没有采到握拳或张开手掌的数据，无法给出建议。")
        print("请按脚本头部说明重新录一遍，注意每段都要保持手势不动。")
        return 1

    print()
    print("=" * 66)
    print("各手势的置信度分布")
    print("=" * 66)
    print("  %-20s %6s %7s %7s %7s %7s %7s"
          % ("手势", "帧数", "最低", "p05", "中位", "p95", "最高"))
    for gesture in sorted(by_gesture, key=lambda g: -len(by_gesture[g])):
        values = sorted(by_gesture[gesture])
        mark = " *" if gesture in SUPPORTED else "  "
        print("%s%-20s %6d %7.3f %7.3f %7.3f %7.3f %7.3f"
              % (mark, gesture, len(values), values[0],
                 percentile(values, 0.05), percentile(values, 0.50),
                 percentile(values, 0.95), values[-1]))
    print("  （* = 本项目认识的手势；其余都是不该触发转向的类别）")

    # ---- 建议阈值 ----
    #
    # 注意这里**不**拿"别的手势的分数"来比。像 Victory 这种类别，
    # 它是被"类别名不在 GESTURE_TO_INTENT 里"挡掉的，和 --min-score
    # 一点关系都没有 —— 阈值只在同一个类别内部起作用。
    # 拿两者比会得出"无法区分"的错误结论。
    #
    # --min-score 在这里真正的职责：
    #   定太高 -> 正常做手势时有一部分帧被判无效 -> 手势"时断时续"
    #             -> 车一顿一顿地转向/停车
    #   定太低 -> 过于边缘的识别也被当真
    # 所以选法是：取"几乎不丢帧"的最高值。
    print()
    print("=" * 66)
    print("建议的 --min-score")
    print("=" * 66)
    print("  先看不同阈值下，本次录制的每个手势有多少帧能通过（掉得越多车越顿）：")
    print()
    print("    %-8s %-16s %-16s" % ("阈值", "Closed_Fist", "Open_Palm"))

    candidates = [round(0.30 + 0.05 * i, 2) for i in range(13)]   # 0.30~0.90
    pass_table = {}
    for t in candidates:
        cells = []
        for g in SUPPORTED:
            values = by_gesture.get(g, [])
            if values:
                rate = sum(1 for v in values if v >= t) / len(values)
                cells.append("%5.1f%% (%d帧)" % (rate * 100,
                                                 sum(1 for v in values if v >= t)))
            else:
                cells.append("     -      ")
        pass_table[t] = cells
        mark = "  <= 默认" if abs(t - 0.60) < 1e-9 else ""
        print("    %-8.2f %-16s %-16s%s" % (t, cells[0], cells[1], mark))

    # 取满足"每个有效手势至少 98% 的帧通过"的最高阈值
    target = 0.98
    chosen = None
    for t in candidates:
        ok = True
        for g in SUPPORTED:
            values = by_gesture.get(g, [])
            if not values:
                continue
            if sum(1 for v in values if v >= t) / len(values) < target:
                ok = False
                break
        if ok:
            chosen = t
    if chosen is None:
        chosen = 0.30

    print()
    print("  ==> 建议 --min-score %.2f" % chosen)
    print("      这是「每个有效手势仍有 %.0f%% 的帧通过」的最高阈值，"
          % (target * 100))
    print("      也就是既能滤掉最边缘的识别，又不会让手势中途断掉。")

    default_drop = []
    for g in SUPPORTED:
        values = by_gesture.get(g, [])
        if values:
            default_drop.append(
                (g, 100.0 * sum(1 for v in values if v < 0.60) / len(values)))
    if default_drop:
        print()
        print("  对比默认值 0.60：")
        for g, pct in default_drop:
            print("    %-14s 有 %.0f%% 的帧会被判无效"
                  % (g, pct))
        if any(pct > 5 for _g, pct in default_drop):
            print("    这些帧会打断手势，表现为车一顿一顿地转/停，")
            print("    所以建议按上面的值调低。")

    print()
    print("  另外说明：")
    print("    - Victory 等别的手势不参与这个阈值，它们会被「类别不支持」挡住")
    print("    - 误触发风险（比如某个姿势被误认成握拳）无法从无标注的记录里")
    print("      算出来，需要在实机上观察；--hold-ms 是防它的主要手段")

    return _hold_report(tracks)


def _hold_report(tracks):
    # ---- 顺带看 --hold-ms ----
    runs = longest_runs(tracks)
    print()
    print("=" * 66)
    print("参考：连续稳定时长（用来判断 --hold-ms）")
    print("=" * 66)
    for g in SUPPORTED:
        if g in runs:
            print("  %-18s 最长连续 %.1f 秒" % (g, runs[g] / 1000.0))
    print("  判定时间 --hold-ms 应当远小于上面的时长，默认 200ms 通常就够。")
    print("  如果最长连续时长只有零点几秒，说明手势保持不稳，")
    print("  先把 --hold-ms 调回 200 以下或改善光照/距离，而不是硬扛。")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="分析手势置信度记录")
    parser.add_argument("csv_file", help="--log-scores 生成的文件")
    args = parser.parse_args(argv)

    by_gesture, stats, tracks = load(args.csv_file)
    code = report(by_gesture, stats, tracks)
    print()
    print("录好的参数可以这样用：")
    print("  python gesture_control.py --port COM4 --min-score <上面的值>")
    return code


if __name__ == "__main__":
    sys.exit(main())
