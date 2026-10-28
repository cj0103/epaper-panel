# -*- coding: utf-8 -*-
"""
雅黑阈值扫描：找出「换雅黑后能通过 bdfconv 且视觉重量接近黑体」的参数。

两个维度同时看：
  1) 可行性：bdfconv -f 1 是否报 "glyph too large"（v1 单字形 255B 硬上限）
  2) 观感：每字平均墨点数（ink density）。墨点太少 → 墨水屏上发淡；
           太多 → 小字号粘连。目标是让雅黑的墨量 ≈ 黑体。

用法：
  E:\\software\\python311\\python.exe tools\\font_threshold_sweep.py
"""
import subprocess
import sys
from pathlib import Path

from PIL import ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_bdf

ROOT = Path(__file__).resolve().parent.parent
U8G2 = ROOT / "tools" / "u8g2tools"
BDFCONV = U8G2 / "bdfconv.exe"
WORK = U8G2 / "work"

MAP = ("$20-$7e,$4e00-$9fff,$a0a1-$a1fe,$2000-$206f,$3000-$303f,$ff00-$ffef,"
       "$00b7,$00d7,$00f7")

SIMHEI = (r"C:\Windows\Fonts\simhei.ttf", 0)
MSYH = (r"C:\Windows\Fonts\msyh.ttc", 0)
MSYHBD = (r"C:\Windows\Fonts\msyhbd.ttc", 0)

PROBE_CHARS = ("课上同学们认真地听老师讲课窗外的树叶沙沙作响语文数学英语美术"
               "体育音乐书法我的妈妈哪吒过一天")


def build_mode_for(px):
    return 2 if px in (28, 34) else 0


def ink_density(path, index, px, thr):
    """每字平均墨点数（只统计探针字符集）。"""
    f = ImageFont.truetype(path, size=px * make_bdf.SUPERSAMPLE, index=index)
    tot = 0
    n = 0
    for ch in PROBE_CHARS:
        r = make_bdf.render_glyph(ch, px, f, thr)
        if r is None:
            continue
        tot += sum(sum(row) for row in r)
        n += 1
    return tot / max(1, n)


def try_build(tag, path, index, px, build, thr, chars):
    f = ImageFont.truetype(path, size=px * make_bdf.SUPERSAMPLE, index=index)
    WORK.mkdir(parents=True, exist_ok=True)
    bdf = WORK / ("sweep_%s_%d_%d.bdf" % (tag, px, thr))
    out_c = WORK / ("sweep_%s_%d_%d.c" % (tag, px, thr))
    make_bdf.write_bdf(str(bdf), chars, px, font=f, threshold=thr)
    p = subprocess.run([str(BDFCONV), "-f", "1", "-b", str(build), "-m", MAP,
                        str(bdf), "-o", str(out_c)],
                       capture_output=True, text=True)
    txt = (p.stdout or "") + (p.stderr or "")
    ok = (p.returncode == 0 and "Error" not in txt and out_c.exists())
    return ok, (out_c.stat().st_size if out_c.exists() else 0), txt.strip()


def main():
    if not BDFCONV.exists():
        print("缺少 bdfconv.exe")
        return 1
    chars = make_bdf.collect_chars()
    print("== 1) 黑体基线（现行参数）==")
    for px in (28, 34, 44):
        b, t = BASE = build_mode_for(px), (110 if px in (28, 34) else 180)
        dens = ink_density(SIMHEI[0], 0, px, t)
        ok, size, msg = try_build("simhei", SIMHEI[0], 0, px, b, t, chars)
        print("  simhei %2dpx thr=%3d build=%d 墨量/字=%6.1f  v1=%8d %s" %
              (px, t, b, dens, size, "OK" if ok else "FAIL:" + msg[-60:]))

    print()
    print("== 2) 雅黑 Regular 阈值扫描 ==")
    print("  %-6s %-5s %-8s %-10s %-10s %s" %
          ("px", "thr", "build", "墨量/字", "v1字节", "结果"))
    best = {}
    for px in (28, 34, 44):
        for thr in (60, 70, 80, 90, 100, 110, 130, 150, 170, 190, 210):
            b = build_mode_for(px)
            dens = ink_density(MSYH[0], 0, px, thr)
            ok, size, msg = try_build("msyh", MSYH[0], 0, px, b, thr, chars)
            print("  %-6d %-5d %-8d %-10.1f %-10d %s" %
                  (px, thr, b, dens, size,
                   "OK" if ok else "FAIL:" + msg.splitlines()[-1][:50]))
            if ok and px not in best:
                best[px] = (thr, size, dens)
            if ok and dens >= ink_density(SIMHEI[0], 0, px,
                                          110 if px in (28, 34) else 180):
                best[px] = (thr, size, dens)
                break
    print()
    print("== 3) 结论（雅黑可行参数）==")
    for px in (28, 34, 44):
        if px in best:
            thr, size, dens = best[px]
            print("  %2dpx: 最小可用阈值 thr=%d → v1=%d 字节 (%.0f KB), 墨量/字=%.1f"
                  % (px, thr, size, size / 1024.0, dens))
        else:
            print("  %2dpx: 全部阈值都失败" % px)
    return 0


if __name__ == "__main__":
    sys.exit(main())
