# -*- coding: utf-8 -*-
"""
雅黑 44px 的极限参数探针 + 42px 替代方案定档。

背景：u8g2 v1 格式里每个字形有一个 1 字节的尺寸字段 → 单字形硬上限 255B。
bdfconv 编码时一旦某个字形超限就报
    RLE Compress: Error, glyph too large, encoding=<码位>
并**整个字库生成失败**。

雅黑笔画比黑体密，44px 档在现行参数（thr=180, build=0）下必炸。
本脚本回答三个问题：
  1. 44px 靠"提高阈值"能不能救回来？极限在哪？
  2. 44px 靠"换 build mode"能不能救回来？
  3. 如果 44px 无解，42px 能不能顶上？体积/阈值定在哪？

用法：
  E:\\software\\python311\\python.exe tools\\font_44px_probe.py
"""
import subprocess
import sys
from pathlib import Path

from PIL import ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_bdf
from parse_cfont import parse_c_font

ROOT = Path(__file__).resolve().parent.parent
U8G2 = ROOT / "tools" / "u8g2tools"
BDFCONV = U8G2 / "bdfconv.exe"
WORK = U8G2 / "work"

MAP = ("$20-$7e,$4e00-$9fff,$a0a1-$a1fe,$2000-$206f,$3000-$303f,$ff00-$ffef,"
       "$00b7,$00d7,$00f7")

MSYH = (r"C:\Windows\Fonts\msyh.ttc", 0)


def build(px, thr, build_mode, chars, path=MSYH[0], index=MSYH[1]):
    f = ImageFont.truetype(path, size=px * make_bdf.SUPERSAMPLE, index=index)
    WORK.mkdir(parents=True, exist_ok=True)
    bdf = WORK / ("p44_%d_%d_%d.bdf" % (px, thr, build_mode))
    out_c = WORK / ("p44_%d_%d_%d.c" % (px, thr, build_mode))
    make_bdf.write_bdf(str(bdf), chars, px, font=f, threshold=thr)
    p = subprocess.run([str(BDFCONV), "-f", "1", "-b", str(build_mode),
                        "-m", MAP, str(bdf), "-o", str(out_c)],
                       capture_output=True, text=True)
    txt = ((p.stdout or "") + (p.stderr or "")).strip()
    if p.returncode != 0 or "Error" in txt:
        err = [l for l in txt.splitlines() if l.strip()]
        return None, (err[-1][:70] if err else "rc=%d" % p.returncode)
    name, data, declared = parse_c_font(str(out_c))
    return len(data), ""


def main():
    if not BDFCONV.exists():
        print("缺少 bdfconv.exe")
        return 1
    chars = make_bdf.collect_chars()

    print("== 1) 雅黑 44px：提高阈值能不能救 ==")
    for thr in (180, 200, 210, 220, 230, 235, 240, 245, 250, 254):
        sz, err = build(44, thr, 0, chars)
        print("  thr=%3d build=0 -> %s" % (thr, ("%d 字节" % sz) if sz else "FAIL: " + err))

    print()
    print("== 2) 雅黑 44px：换 build mode 能不能救（thr=180）==")
    for b in (0, 1, 2, 3):
        sz, err = build(44, 180, b, chars)
        print("  thr=180 build=%d -> %s" % (b, ("%d 字节" % sz) if sz else "FAIL: " + err))

    print()
    print("== 3) 雅黑 42px：阈值定档 ==")
    for thr in (180, 160, 140, 120, 100, 80):
        sz, err = build(42, thr, 0, chars)
        print("  thr=%3d build=0 -> %s" % (thr, ("%d 字节" % sz) if sz else "FAIL: " + err))

    print()
    print("== 4) 雅黑 28/34px：把阈值降到「与黑体同墨量」的档位 ==")
    for px in (28, 34):
        for thr in (110, 90, 80, 70, 60):
            sz, err = build(px, thr, 2, chars)
            print("  %2dpx thr=%3d build=2 -> %s" %
                  (px, thr, ("%d 字节" % sz) if sz else "FAIL: " + err))
    return 0


if __name__ == "__main__":
    sys.exit(main())
