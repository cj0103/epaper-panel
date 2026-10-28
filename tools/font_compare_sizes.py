# -*- coding: utf-8 -*-
"""
字号扩展对比：黑体 vs 雅黑，覆盖 24 / 26 / 28 / 34 / 42(44) px。

同时输出「为什么肉眼看差别不大」的量化指标：
  - 墨量差：同字号下两字体点亮的像素数之比
  - 结构差：逐像素比对，两字体点亮的像素重合率（IoU）
    IoU 高 = 绝大多数像素位置相同 = 只是笔画边缘差一两格 = 看着几乎一样

用法：
  E:\\software\\python311\\python.exe tools\\font_compare_sizes.py
  → tools/_font_sizes.png
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_bdf

ROOT = Path(__file__).resolve().parent.parent

SIMHEI = (r"C:\Windows\Fonts\simhei.ttf", 0)
MSYH = (r"C:\Windows\Fonts\msyh.ttc", 0)

# (字号, 阈值) —— 阈值沿用流水线现行值；24/26/42 为本次新增档位
SIZES = [(24, 110), (26, 110), (28, 110), (34, 110), (44, 180)]

SAMPLE = "课堂上，同学们认真地听老师讲课"
SAMPLE2 = "语文、数学、英语、美术、体育"


def font_for(path, index, px):
    return ImageFont.truetype(path, size=px * make_bdf.SUPERSAMPLE, index=index)


def stats(px, thr):
    """墨量 + 骨架重合率 + 垂直落位差。

    对齐基准用**基线**（baseline），不是字格左上角、也不是墨迹框：
    两个字体都是等宽（advance = 字号），固件按基线画字，所以基线对齐
    才是肉眼实际看到的重叠关系。水平方向按字格中心对齐（等宽字格中心
    即视觉中心）。
    """
    fa = font_for(SIMHEI[0], SIMHEI[1], px)
    fb = font_for(MSYH[0], MSYH[1], px)
    base_a = int(round(make_bdf.baseline_row(px, fa)))
    base_b = int(round(make_bdf.baseline_row(px, fb)))
    tot_a = tot_b = inter = union = 0
    dy_list = []
    for ch in SAMPLE + SAMPLE2:
        ra = make_bdf.render_glyph(ch, px, fa, thr)
        rb = make_bdf.render_glyph(ch, px, fb, thr)
        if ra is None or rb is None:
            continue
        ia = [y for y in range(px) if any(ra[y])]
        ib = [y for y in range(px) if any(rb[y])]
        xa = [x for y in range(px) for x in range(px) if ra[y][x]]
        xb = [x for y in range(px) for x in range(px) if rb[y][x]]
        if not ia or not ib:
            continue
        # 墨底相对基线的距离（负=基线以下）
        dy_list.append((base_a - ia[-1]) - (base_b - ib[-1]))
        tot_a += sum(sum(r) for r in ra)
        tot_b += sum(sum(r) for r in rb)
        # 平移到同一坐标系：垂直对齐基线，水平对齐字格中心
        off_ay, off_ax = ia[0], (xa[0] + xa[1]) // 2
        off_by, off_bx = ib[0], (xb[0] + xb[1]) // 2
        canvas = {}
        for dy, row in enumerate(ra[ia[0]:ia[-1] + 1], start=ia[0]):
            for dx in range(xa[0], xa[1] + 1):
                if row[dx]:
                    canvas[(dy - off_ay, dx - off_ax)] = 1
        bmp_b = set()
        for dy, row in enumerate(rb[ib[0]:ib[-1] + 1], start=ib[0]):
            for dx in range(xb[0], xb[1] + 1):
                if row[dx]:
                    bmp_b.add((dy - off_by, dx - off_bx))
        inter += len(set(canvas) & bmp_b)
        union += len(set(canvas) | bmp_b)
    iou = 100.0 * inter / union if union else 100.0
    dy_mean = sum(abs(v) for v in dy_list) / max(1, len(dy_list))
    return tot_a, tot_b, iou, dy_mean


def draw_line(cv, font, cache, text, px, x, y):
    for ch in text:
        key = (id(font), ch)
        if key not in cache:
            cache[key] = make_bdf.render_glyph(ch, px, font)
        r = cache[key]
        if r is not None:
            for gy in range(px):
                if not any(r[gy]):
                    continue
                for gx in range(px):
                    if r[gy][gx]:
                        cv.putpixel((x + gx, y + gy), 0)
        x += px


def main():
    left = 12
    max_cols = max(len(SAMPLE), len(SAMPLE2))
    width = max_cols * 44 + 24

    height = 26
    for px, _ in SIZES:
        height += (px * 2 + 34) * 2 + 16
    height += 70

    cv = Image.new("L", (width, height), 255)
    d = ImageDraw.Draw(cv)
    d.text((left, 6), "黑体 vs 雅黑 —— 全字号段对比（含新增 24px / 26px）", fill=0)

    y = 26
    cache = {}
    rows = []
    for px, thr in SIZES:
        a, b, iou, dy = stats(px, thr)
        rows.append((px, thr, a, b, iou, dy))
        for name, path, index in (("黑体 SimHei", SIMHEI[0], SIMHEI[1]),
                                  ("雅黑 YaHei", MSYH[0], MSYH[1])):
            f = font_for(path, index, px)
            d.text((left, y), "%s  %dpx" % (name, px), fill=0)
            yy = y + 15
            draw_line(cv, f, cache, SAMPLE, px, left, yy)
            draw_line(cv, f, cache, SAMPLE2, px, left, yy + px + 4)
            y += px * 2 + 34
        tag = "" if px != 44 else "（雅黑44px不可行，此处用42px渲染）"
        d.text((left + 300, y - 14),
               "墨量 黑%d/雅%d（雅+%d%%）  骨架重合 %.0f%%  基线落位差 %.1fpx  %s"
               % (a, b, round(100.0 * (b - a) / a), iou, dy, tag), fill=100)
        d.line([(0, y - 6), (width, y - 6)], fill=175)
        y += 10

    d.text((left, y), "骨架重合率：基线对齐、字格水平居中后逐像素的重合程度 —— 高 = 骨架几乎一样 = 肉眼觉得「差不多」。", fill=0)
    d.text((left, y + 15), "基线落位差：墨迹底边相对基线的平均偏离 —— 大 = 同一行里两个字上下不在一条线上。", fill=0)

    out = ROOT / "tools" / "_font_sizes.png"
    cv.save(str(out))
    print("saved:", out)
    print()
    print("== 量化指标 ==")
    print("%-6s %-6s %10s %10s %10s %12s %14s" %
          ("字号", "阈值", "黑体墨量", "雅黑墨量", "墨量差", "骨架重合率", "基线落位差"))
    for px, thr, a, b, iou, dy in rows:
        print("%-6d %-6d %10d %10d %+9.1f%% %11.1f%% %12.2f px" %
              (px, thr, a, b, 100.0 * (b - a) / a, iou, dy))
    return 0


if __name__ == "__main__":
    sys.exit(main())
