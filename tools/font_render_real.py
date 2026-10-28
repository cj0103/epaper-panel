# -*- coding: utf-8 -*-
"""
真实字库渲染对比：黑体 vs 雅黑，覆盖 24 / 26 / 28 / 34 / 44(42) px。

与 font_compare*.py 的区别：那批脚本用 Pillow 直接渲染示意；本脚本
**真的走一遍流水线**（BDF → 官方 bdfconv -f 1），再用 v1_verify.Decoder
（逐行复刻 U8g2_for_Adafruit_GFX 解析器）解出字形位图来画。
→ 图上每一个点都是墨水屏上真正会亮的点。

用法：
  E:\\software\\python311\\python.exe tools\\font_render_real.py
  → tools/_font_real.png
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_bdf
from parse_cfont import parse_c_font
from v1_verify import FontInfo, find_glyph_data, Decoder

ROOT = Path(__file__).resolve().parent.parent
U8G2 = ROOT / "tools" / "u8g2tools"
BDFCONV = U8G2 / "bdfconv.exe"
WORK = U8G2 / "work"

MAP = ("$20-$7e,$4e00-$9fff,$a0a1-$a1fe,$2000-$206f,$3000-$303f,$ff00-$ffef,"
       "$00b7,$00d7,$00f7")

FONTS = [
    ("黑体 SimHei", r"C:\Windows\Fonts\simhei.ttf", 0,
     [(24, 110, 2), (26, 110, 2), (28, 110, 2), (34, 110, 2), (44, 180, 0)]),
    ("雅黑 YaHei", r"C:\Windows\Fonts\msyh.ttc", 0,
     [(24, 110, 2), (26, 110, 2), (28, 110, 2), (34, 110, 2), (42, 180, 0)]),
]

SAMPLE = "课堂上同学们认真"


def build_font(path, index, px, thr, build_mode, chars):
    f = ImageFont.truetype(path, size=px * make_bdf.SUPERSAMPLE, index=index)
    tag = Path(path).stem
    bdf = WORK / ("real_%s_%d.bdf" % (tag, px))
    out_c = WORK / ("real_%s_%d.c" % (tag, px))
    make_bdf.write_bdf(str(bdf), chars, px, font=f, threshold=thr)
    p = subprocess.run([str(BDFCONV), "-f", "1", "-b", str(build_mode),
                        "-m", MAP, str(bdf), "-o", str(out_c)],
                       capture_output=True, text=True)
    txt = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0 or "Error" in txt:
        err = [l for l in txt.splitlines() if l.strip()]
        raise RuntimeError((err[-1] if err else "rc=%d" % p.returncode)[:80])
    name, data, declared = parse_c_font(str(out_c))
    return data, len(data)


def draw_from_v1(cv, data, info, text, px, x0, y0):
    """用固件同款解码器把字形画到 Image 上（advance = 字号）。"""
    x = x0
    for ch in text:
        if ch == " ":
            x += px
            continue
        off = find_glyph_data(data, info, ord(ch))
        if off is None:
            x += px
            continue
        dec = Decoder(data, info)
        dec.decode_glyph(off)
        w, h = dec.glyph_width, dec.glyph_height
        dx, dy = dec.dx_off, dec.dy_off
        for (lx, ly, is_fg) in dec.pixels:
            if not is_fg:
                continue
            X = x + dx + lx
            Y = y0 + dy + ly
            if 0 <= X < cv.width and 0 <= Y < cv.height:
                cv.putpixel((int(X), int(Y)), 0)
        x += px


def main():
    chars = make_bdf.collect_chars()
    line = SAMPLE
    width = len(line) * 44 + 300

    # 预估高度
    height = 26
    for _, _, _, sizes in FONTS:
        for px, _, _ in sizes:
            height += px + 34
        height += 18
    height += 40

    cv = Image.new("L", (width, height), 255)
    d = ImageDraw.Draw(cv)
    d.text((12, 6), "真实字库渲染（BDF → bdfconv -f 1 → 固件同款 v1 解码器）", fill=0)

    y = 28
    for name, path, index, sizes in FONTS:
        d.text((12, y), name, fill=0)
        y += 18
        for px, thr, bm in sizes:
            try:
                data, size = build_font(path, index, px, thr, bm, chars)
            except RuntimeError as e:
                d.text((24, y), "%2dpx  生成失败：%s" % (px, e), fill=150)
                y += px + 20
                continue
            info = FontInfo(data)
            draw_from_v1(cv, data, info, line, px, 24, y)
            d.text((len(line) * px + 40, y + px // 2 - 6),
                   "%dpx · %s · %6.0f KB" % (px, "thr%d/b%d" % (thr, bm), size / 1024.0),
                   fill=90)
            y += px + 22
        d.line([(0, y - 8), (width, y - 8)], fill=180)
        y += 10

    out = ROOT / "tools" / "_font_real.png"
    cv.save(str(out))
    print("saved:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
