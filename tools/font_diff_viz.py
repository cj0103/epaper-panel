# -*- coding: utf-8 -*-
"""
差异放大型对比图：黑体 vs 雅黑，含 24 / 26 / 28 / 34 / 42(44) px。

三段式，直接回答"为什么看着差不多"：
  行 1  黑体二值点阵
  行 2  雅黑二值点阵          ← 与前一行逐行对照，肉眼看差异
  行 3  差异图：黑体独有=■ 雅黑独有=□ 两者共有=·（灰点）
        → 灰点铺满 = 骨架其实高度重叠，差别只在笔画边缘那一两格

量化指标：
  墨量      —— 同字号点亮的像素数（决定"看起来多黑")
  共有率    —— 两字体同时点亮的像素占各自墨量的比例（比 IoU 更贴肉眼感受）
  落位差    —— 墨底相对基线的平均偏离（决定同一行里是否上下不齐）

用法：
  E:\\software\\python311\\python.exe tools\\font_diff_viz.py
  → tools/_font_diff.png
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_bdf

ROOT = Path(__file__).resolve().parent.parent

SIMHEI = (r"C:\Windows\Fonts\simhei.ttf", 0)
MSYH = (r"C:\Windows\Fonts\msyh.ttc", 0)

SIZES = [(24, 110), (26, 110), (28, 110), (34, 110), (44, 180)]
SAMPLE = "课堂上同学们认真"


def font_for(path, index, px):
    return ImageFont.truetype(path, size=px * make_bdf.SUPERSAMPLE, index=index)


def analyze(px, thr):
    fa = font_for(SIMHEI[0], SIMHEI[1], px)
    fb = font_for(MSYH[0], MSYH[1], px)
    base_a = int(round(make_bdf.baseline_row(px, fa)))
    base_b = int(round(make_bdf.baseline_row(px, fb)))
    na = nb = both = 0
    dy = []
    for ch in SAMPLE:
        ra = make_bdf.render_glyph(ch, px, fa, thr)
        rb = make_bdf.render_glyph(ch, px, fb, thr)
        if ra is None or rb is None:
            continue
        A = {(y, x) for y in range(px) for x in range(px) if ra[y][x]}
        B = {(y, x) for y in range(px) for x in range(px) if rb[y][x]}
        na += len(A)
        nb += len(B)
        both += len(A & B)
        ia = [y for y in range(px) if any(ra[y])]
        ib = [y for y in range(px) if any(rb[y])]
        dy.append((base_a - ia[-1]) - (base_b - ib[-1]))
    return dict(na=na, nb=nb,
                both=100.0 * both / max(1, min(na, nb)),
                dy=sum(abs(v) for v in dy) / max(1, len(dy)))


def draw_row(cv, font, cache, px, y, x0=12):
    x = x0
    for ch in SAMPLE:
        key = (id(font), ch)
        if key not in cache:
            cache[key] = make_bdf.render_glyph(ch, px, font)
        r = cache[key]
        if r is not None:
            for gy in range(len(r)):
                for gx in range(len(r[gy])):
                    if r[gy][gx]:
                        cv.putpixel((x + gx, y + gy), 0)
        x += px


def draw_diff(cv, fa, fb, cache, px, thr, y, x0=12):
    """共有=浅灰点  黑体独有=黑  雅黑独有=中灰"""
    x = x0
    for ch in SAMPLE:
        ka = (id(fa), ch, px, thr)
        kb = (id(fb), ch, px, thr)
        if ka not in cache:
            cache[ka] = make_bdf.render_glyph(ch, px, fa, thr)
        if kb not in cache:
            cache[kb] = make_bdf.render_glyph(ch, px, fb, thr)
        ra, rb = cache[ka], cache[kb]
        if ra is not None and rb is not None:
            for gy in range(min(len(ra), len(rb))):
                for gx in range(min(len(ra[gy]), len(rb[gy]))):
                    a, b = ra[gy][gx], rb[gy][gx]
                    if a and b:
                        cv.putpixel((x + gx, y + gy), 205)   # 共有：浅灰
                    elif a:
                        cv.putpixel((x + gx, y + gy), 0)     # 黑体独有：黑
                    elif b:
                        cv.putpixel((x + gx, y + gy), 120)   # 雅黑独有：中灰
        x += px


def main():
    px_max = SIZES[-1][0]
    width = len(SAMPLE) * px_max + 340
    height = 26
    for px, _ in SIZES:
        height += px * 3 + 76
    height += 60

    cv = Image.new("L", (width, height), 255)
    d = ImageDraw.Draw(cv)
    d.text((12, 6), "黑体 vs 雅黑 —— 全字号段（含新增 24 / 26px）+ 像素差异图", fill=0)

    y = 28
    cache = {}
    rows = []
    for px, thr in SIZES:
        st = analyze(px, thr)
        rows.append((px, thr, st))
        fa = font_for(SIMHEI[0], SIMHEI[1], px)
        fb = font_for(MSYH[0], MSYH[1], px)

        d.text((12, y), "黑体 %dpx" % px, fill=0)
        draw_row(cv, fa, cache, px, y + 15)
        y += px + 20
        d.text((12, y), "雅黑 %dpx" % px, fill=0)
        draw_row(cv, fb, cache, px, y + 15)
        y += px + 20
        d.text((12, y), "差异", fill=0)
        draw_diff(cv, fa, fb, cache, px, thr, y + 15)
        note = "" if px != 44 else "（雅黑44px不可行，用42px渲染）"
        d.text((len(SAMPLE) * px + 24, y + 4),
               "墨量 黑%d / 雅%d（雅+%d%%）" % (st["na"], st["nb"],
                                                round(100.0 * (st["nb"] - st["na"]) / st["na"])),
               fill=0)
        d.text((len(SAMPLE) * px + 24, y + 20),
               "共有像素 %.0f%%   落位差 %.2fpx" % (st["both"], st["dy"]), fill=60)
        d.text((len(SAMPLE) * px + 24, y + 36),
               "黑=黑体独有 中灰=雅黑独有 浅灰=两者共有", fill=110)
        y += px + 30
        d.line([(0, y - 8), (width, y - 8)], fill=180)

    d.text((12, y), "浅灰铺得越满 → 骨架越重叠 → 肉眼越觉得「差不多」；", fill=0)
    d.text((12, y + 15), "           黑/中灰只贴在笔画边缘一两格 → 这正是差异的全部来源。", fill=0)

    out = ROOT / "tools" / "_font_diff.png"
    cv.save(str(out))
    print("saved:", out)
    print()
    print("== 量化指标 ==")
    print("%-6s %-6s %10s %10s %10s %12s %12s" %
          ("字号", "阈值", "黑体墨量", "雅黑墨量", "墨量差", "共有像素", "落位差"))
    for px, thr, st in rows:
        print("%-6d %-6d %10d %10d %+9.1f%% %11.1f%% %10.2f px" %
              (px, thr, st["na"], st["nb"],
               100.0 * (st["nb"] - st["na"]) / st["na"], st["both"], st["dy"]))
    return 0


if __name__ == "__main__":
    main()
