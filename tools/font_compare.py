# -*- coding: utf-8 -*-
"""
字体对比图：黑体(SimHei，现行) vs 雅黑(Microsoft YaHei，推荐方案)。

**不烧板就能看到效果**：复用 make_bdf.py 里那套渲染参数
（4× 超采样 → LANCZOS 缩回 → 阈值二值化），图上看到的就是进墨水屏前的位图。

推荐参数（由 tools/font_decide.py 实测定档）：
  28px thr=110 build=2   34px thr=110 build=2   42px thr=180 build=0
  （44px 雅黑在 v1 格式下过不了 255B/字形 上限，故大档降为 42px）

用法：
  E:\\software\\python311\\python.exe tools\\font_compare.py
  → tools/_font_compare.png

配套工具：
  font_size_probe.py     体积 / 255B 上限实测
  font_threshold_sweep.py 阈值扫描
  font_decode_check.py   v1 解码器像素级验证
  font_decide.py         最终定档
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_bdf

ROOT = Path(__file__).resolve().parent.parent

# (标签, 字体文件, TTC face index, [(字号, 阈值), ...])
SETS = [
    ("■ 现行：黑体 SimHei", r"C:\Windows\Fonts\simhei.ttf", 0,
     [(28, 110), (34, 110), (44, 180)]),
    ("■ 推荐：雅黑 Microsoft YaHei", r"C:\Windows\Fonts\msyh.ttc", 0,
     [(28, 110), (34, 110), (42, 180)]),
]

SAMPLE = "课堂上，同学们认真地听老师讲课，窗外的树叶沙沙作响。"
SAMPLE2 = "语文、数学、英语、美术、体育、音乐、书法"


def font_for(path, index, px):
    """4× 超采样字体（与 make_bdf.get_font 同参）。"""
    return ImageFont.truetype(path, size=px * make_bdf.SUPERSAMPLE, index=index)


def draw_line(cv, font, cache, text, px, x, y):
    """按「advance = 字号」的等宽格逐字落墨（与固件渲染层一致）。"""
    for ch in text:
        key = (id(font), ch)
        if key not in cache:
            cache[key] = make_bdf.render_glyph(ch, px, font)
        r = cache[key]
        if r is not None:
            for gy in range(px):
                line = r[gy]
                if not any(line):
                    continue
                for gx in range(px):
                    if line[gx]:
                        cv.putpixel((x + gx, y + gy), 0)
        x += px  # advance 恒等于字号
    return x


def main():
    label_h = 30
    left = 12
    max_cols = max(len(SAMPLE), len(SAMPLE2))
    width = max_cols * 44 + 24

    height = label_h
    for _, _, _, sizes in SETS:
        for px, _ in sizes:
            height += px * 2 + 20
        height += 14
    height += 46

    cv = Image.new("L", (width, height), 255)
    d = ImageDraw.Draw(cv)
    d.text((left, 8), "墨水屏字形对比：黑体(现行) vs 雅黑(推荐)", fill=0)

    y = label_h
    cache = {}
    for name, path, index, sizes in SETS:
        d.text((left, y), name, fill=0)
        y += 16
        for px, thr in sizes:
            f = font_for(path, index, px)
            d.text((left, y), "  %dpx  threshold=%d" % (px, thr), fill=0)
            yy = y + 15
            draw_line(cv, f, cache, SAMPLE, px, left, yy)
            draw_line(cv, f, cache, SAMPLE2, px, left, yy + px + 4)
            y += px * 2 + 20
        d.line([(0, y - 6), (width, y - 6)], fill=170)
        y += 8

    d.text((left, y), "注：雅黑 44px 在 u8g2 v1 格式下超出单字形 255B 硬上限，"
                      "bdfconv 直接报错，故大档改用 42px。", fill=0)
    d.text((left, y + 14), "    28/34px 参数与黑体完全一致；"
                           "42px 仍为等宽（advance = 字号），排版规则不变。", fill=0)

    out = ROOT / "tools" / "_font_compare.png"
    cv.save(str(out))
    print("saved:", out)


if __name__ == "__main__":
    main()
