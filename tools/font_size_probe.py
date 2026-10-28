# -*- coding: utf-8 -*-
"""
字库体积 / v1 上限探针：换字体前先把"数字"摸清楚，不烧板。

对每个 (字体, 字号, 阈值)：
  1. make_bdf 渲染出 BDF
  2. 官方 bdfconv -f 1 转成 u8g2 v1 格式
  3. 报告**二进制字库真实体积**、字形数、**单字形最大字节数**（v1 硬上限 255B）

⚠ 体积口径：bdfconv 产物是 C 源码（八进制转义，每字节 4 个字符），
   直接看文件大小会虚高 ~2.8 倍。必须用 parse_c_font 还原成二进制再量。

v1 结构（见 U8g2_for_Adafruit_GFX.cpp 的 u8g2_read_font_info）：
  [0..22]   字体头（glyph_cnt 是 unicode 查找表项数，不是字形数）
  [23..]    字形区：每项 = 编码(2B, 大端) + 尺寸(1B) + 位流(size B)
  [start_pos_unicode]  unicode 查找表：每项 4 字节 = 偏移增量(2B) + 最大编码(2B)

用法：
  E:\\software\\python311\\python.exe tools\\font_size_probe.py
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

FONTS = [
    ("simhei", r"C:\Windows\Fonts\simhei.ttf", 0),
    ("msyh", r"C:\Windows\Fonts\msyh.ttc", 0),
    ("msyhbd", r"C:\Windows\Fonts\msyhbd.ttc", 0),
]

# gen_fonts_v1.py 现行配置
BASE_CFG = {28: (2, 110), 34: (2, 110), 44: (0, 180)}


def walk_glyphs(data):
    """走一遍 v1 字形区，返回 [(encoding, size), ...]。"""
    start_unicode = (data[21] << 8) | data[22]
    pos = 23
    out = []
    while pos < start_unicode:
        enc = (data[pos] << 8) | data[pos + 1]
        size = data[pos + 2]
        out.append((enc, size))
        pos += 3 + size
    return out


def build(tag, path, index, px, build_mode, thr, chars):
    f = ImageFont.truetype(path, size=px * make_bdf.SUPERSAMPLE, index=index)
    WORK.mkdir(parents=True, exist_ok=True)
    bdf = WORK / ("probe_%s_%d_%d.bdf" % (tag, px, thr))
    out_c = WORK / ("probe_%s_%d_%d.c" % (tag, px, thr))
    make_bdf.write_bdf(str(bdf), chars, px, font=f, threshold=thr)
    p = subprocess.run([str(BDFCONV), "-f", "1", "-b", str(build_mode), "-m", MAP,
                        str(bdf), "-o", str(out_c)],
                       capture_output=True, text=True)
    txt = ((p.stdout or "") + (p.stderr or "")).strip()
    ok = (p.returncode == 0 and "Error" not in txt and out_c.exists())
    if not ok:
        err = [l for l in txt.splitlines() if l.strip()]
        return dict(ok=False, size=0, n=0, maxg=0,
                    err=(err[-1] if err else "rc=%d" % p.returncode)[:70])
    name, data, declared = parse_c_font(str(out_c))
    g = walk_glyphs(data)
    return dict(ok=True, size=len(data), n=len(g),
                maxg=max((s for _, s in g), default=0),
                over=[e for e, s in g if s > 255][:5], err="")


def main():
    if not BDFCONV.exists():
        print("缺少 bdfconv.exe")
        return 1
    chars = make_bdf.collect_chars()
    print("字符集 %d" % len(chars))
    print()
    print("%-8s %4s %5s %5s %7s %10s %7s %s" %
          ("字体", "px", "build", "thr", "字形数", "二进制字节", "最大字形", "结果"))
    print("-" * 86)
    rows = []
    for tag, path, index in FONTS:
        for px in (28, 34, 44):
            b, thr = BASE_CFG[px]
            r = build(tag, path, index, px, b, thr, chars)
            rows.append((tag, px, r))
            print("%-8s %4d %5d %5d %7d %10d %7d %s" %
                  (tag, px, b, thr, r["n"], r["size"], r["maxg"],
                   "OK" if r["ok"] else "FAIL: " + r["err"]))
    print()
    print("== 相对黑体的体积变化 ==")
    base = {px: r for tag, px, r in rows if tag == "simhei"}
    for tag in ("msyh", "msyhbd"):
        for px in (28, 34, 44):
            r = next(r for t, p, r in rows if t == tag and p == px)
            if r["ok"] and base[px]["size"]:
                d = r["size"] - base[px]["size"]
                print("  %-7s %2dpx: %+d 字节 (%+.1f%%)  基线 %d" %
                      (tag, px, d, 100.0 * d / base[px]["size"], base[px]["size"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
