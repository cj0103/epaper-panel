# -*- coding: utf-8 -*-
"""
换字体定档器：把「雅黑用哪套参数」一次性定死，输出最终推荐表 + 对比图。

判据（三条同时满足才算这一档可用）：
  1. bdfconv -f 1 能通过（v1 单字形 255B 硬上限，雅黑 44px 就卡在这）
  2. 墨量/字 ≈ 黑体同字号（墨水屏是二值的，笔画太淡 = 看着发虚；
     太粗 = 小字号粘连。雅黑本身笔画比黑体细，必须降阈值补回来）
  3. advance 仍等于字号（等宽假设不能破，破了就整版重排）

用法：
  E:\\software\\python311\\python.exe tools\\font_decide.py
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_bdf
from parse_cfont import parse_c_font

ROOT = Path(__file__).resolve().parent.parent
U8G2 = ROOT / "tools" / "u8g2tools"
BDFCONV = U8G2 / "bdfconv.exe"
WORK = U8G2 / "work"

MAP = ("$20-$7e,$4e00-$9fff,$a0a1-$a1fe,$2000-$206f,$3000-$303f,$ff00-$ffef,"
       "$00b7,$00d7,$00f7")

SIMHEI = (r"C:\Windows\Fonts\simhei.ttf", 0)
MSYH = (r"C:\Windows\Fonts\msyh.ttc", 0)

# 探针字集：覆盖常用汉字 + 标点
PROBE = ("课上同学们认真地听老师讲课窗外的树叶沙沙作响语文数学英语美术体育音乐"
         "书法我的妈妈哪吒过一天，。！？；：、“”（）《》")


def ink_density(path, index, px, thr):
    f = ImageFont.truetype(path, size=px * make_bdf.SUPERSAMPLE, index=index)
    tot = 0
    n = 0
    for ch in PROBE:
        r = make_bdf.render_glyph(ch, px, f, thr)
        if r is None:
            continue
        tot += sum(sum(row) for row in r)
        n += 1
    return tot / max(1, n)


def encode_ok(px, thr, build_mode, chars, path=MSYH[0], index=MSYH[1]):
    f = ImageFont.truetype(path, size=px * make_bdf.SUPERSAMPLE, index=index)
    bdf = WORK / ("dec_%d_%d.bdf" % (px, thr))
    out_c = WORK / ("dec_%d_%d.c" % (px, thr))
    make_bdf.write_bdf(str(bdf), chars, px, font=f, threshold=thr)
    p = subprocess.run([str(BDFCONV), "-f", "1", "-b", str(build_mode),
                        "-m", MAP, str(bdf), "-o", str(out_c)],
                       capture_output=True, text=True)
    txt = ((p.stdout or "") + (p.stderr or ""))
    if p.returncode != 0 or "Error" in txt:
        return None
    return parse_c_font(str(out_c))[1]


def main():
    chars = make_bdf.collect_chars()
    print("== 黑体基线（现行参数）==")
    base = {}
    for px, thr, b in ((28, 110, 2), (34, 110, 2), (44, 180, 0)):
        d = ink_density(SIMHEI[0], 0, px, thr)
        data = encode_ok(px, thr, b, chars, SIMHEI[0], 0)
        base[px] = dict(thr=thr, build=b, dens=d, size=len(data) if data else 0)
        print("  %2dpx thr=%3d build=%d  墨量/字=%6.1f  v1=%8d 字节"
              % (px, thr, b, d, base[px]["size"]))

    print()
    print("== 雅黑候选（build 沿用黑体）==")
    print("  %-4s %-5s %-6s %-10s %-10s %s" %
          ("px", "thr", "build", "墨量/字", "v1字节", "判定"))
    cand = {}
    for px, b, thrs in ((28, 2, (110, 90, 80, 70, 60, 50)),
                        (34, 2, (110, 90, 80, 70, 60, 50)),
                        (42, 0, (180, 160, 140, 120, 100, 90))):
        target = base[28 if px == 28 else (34 if px == 34 else 44)]["dens"]
        pick = None
        best = None
        for thr in thrs:
            d = ink_density(MSYH[0], 0, px, thr)
            data = encode_ok(px, thr, b, chars)
            if data is None:
                print("  %-4d %-5d %-6d %-10.1f %-10s FAIL(255B 上限)"
                      % (px, thr, b, d, "-"))
                continue
            diff = 100.0 * (d - target) / target
            verdict = ("墨量接近黑体(%.1f)" % target if abs(diff) < 12
                       else ("偏淡 %.0f%%" % -diff if diff < 0 else "偏粗 %.0f%%" % diff))
            print("  %-4d %-5d %-6d %-10.1f %-10d %s"
                  % (px, thr, b, d, len(data), verdict))
            # 取「墨量最接近黑体」的可编码档位
            if best is None or abs(diff) < abs(best["diff"]):
                best = dict(thr=thr, build=b, dens=d, size=len(data), diff=diff)
        if best:
            pick = best
        cand[px] = pick

    print()
    print("== 最终推荐 ==")
    tot_new = 0
    for px in (28, 34, 42):
        c = cand.get(px)
        if not c:
            print("  %2dpx: 无解" % px)
            continue
        tot_new += c["size"]
        print("  雅黑 %2dpx  thr=%3d build=%d  v1=%8d 字节 (%.0f KB)  墨量/字=%.1f"
              % (px, c["thr"], c["build"], c["size"], c["size"] / 1024.0, c["dens"]))
    tot_old = sum(base[p]["size"] for p in (28, 34, 44))
    print()
    print("  现行黑体 28+34+44 = %d 字节 (%.2f MB)" % (tot_old, tot_old / 1048576.0))
    print("  推荐雅黑 28+34+42 = %d 字节 (%.2f MB)  → %+.1f%%"
          % (tot_new, tot_new / 1048576.0,
             100.0 * (tot_new - tot_old) / tot_old))
    return 0


if __name__ == "__main__":
    sys.exit(main())
