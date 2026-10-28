# -*- coding: utf-8 -*-
"""
换字体的最后一道保险：证明「雅黑位图」能被固件同款 v1 解码器正确读出。

★ 本脚本校验的是**重新生成的**字库（make_bdf 的 FONT_FILE + gen_fonts_v1 的
  SIZES 参数），改档后请同步下面 main() 里的 (px, thr, build) 三元组。
  （之前踩坑：只改了 gen_fonts_v1.py 就宣布定稿，这里仍用旧档参数生成
  小样本字库校验，通过的是"另一份字体"，等于没验。）

做法：
  1. 拿 bdfconv 产出的雅黑 v1 字库（.c）
  2. 用 v1_verify.Decoder（逐行复刻 U8g2_for_Adafruit_GFX 的解析器）解出像素
  3. 与 Pillow 直接渲染的原始字形做**像素级比对**

比对通过 = 换字体后固件的 u8g2 桥接层能正常画出雅黑，不会出现乱码/错位。
这一步不烧板就能做完。

用法：
  E:\\software\\python311\\python.exe tools\\font_decode_check.py
"""
import subprocess
import sys
from pathlib import Path

from PIL import ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_bdf
from parse_cfont import parse_c_font
from v1_verify import FontInfo, Decoder, find_glyph_data

ROOT = Path(__file__).resolve().parent.parent
U8G2 = ROOT / "tools" / "u8g2tools"
BDFCONV = U8G2 / "bdfconv.exe"
WORK = U8G2 / "work"

MAP = ("$20-$7e,$4e00-$9fff,$a0a1-$a1fe,$2000-$206f,$3000-$303f,$ff00-$ffef,"
       "$00b7,$00d7,$00f7")

MSYH = (r"C:\Windows\Fonts\msyh.ttc", 0)
PROBE = "课上同学们听老师讲课窗外树叶沙沙响语文数学英语美术体育音乐书法"


def make_font(path, index, px, thr, build_mode, chars):
    f = ImageFont.truetype(path, size=px * make_bdf.SUPERSAMPLE, index=index)
    bdf = WORK / ("chk_%d.bdf" % px)
    out_c = WORK / ("chk_%d.c" % px)
    make_bdf.write_bdf(str(bdf), chars, px, font=f, threshold=thr)
    p = subprocess.run([str(BDFCONV), "-f", "1", "-b", str(build_mode),
                        "-m", MAP, str(bdf), "-o", str(out_c)],
                       capture_output=True, text=True)
    txt = ((p.stdout or "") + (p.stderr or ""))
    if p.returncode != 0 or "Error" in txt:
        raise RuntimeError("bdfconv 失败: %s" % txt[-300:])
    return parse_c_font(str(out_c))[1]


def bitmap_from_decoder(data, info, ch):
    """解出字形位图（相对 ink 框的 0/1 矩阵）与 advance。"""
    off = find_glyph_data(data, info, ord(ch))
    if off is None:
        return None, None
    dec = Decoder(data, info)
    adv = dec.decode_glyph(off)
    w, h = dec.glyph_width, dec.glyph_height
    bm = [[0] * w for _ in range(h)]
    for (lx, ly, is_fg) in dec.pixels:
        if 0 <= ly < h and 0 <= lx < w:
            bm[ly][lx] = 1 if is_fg else 0
    return bm, adv


def crop_to_ink(bm):
    """裁到墨迹包围盒。

    build mode >=1 时 bdfconv 会把字形补齐到「同一批字形的统一宽高」，
    所以解码出来的位图比原始墨迹框大一圈（四周是白）。比对时必须两边
    都裁到墨迹框再比，否则 build=2 的字库会全部报"不一致"。
    """
    ys = [y for y in range(len(bm)) if any(bm[y])]
    if not ys:
        return None
    xs = [x for y in range(len(bm)) for x in range(len(bm[y])) if bm[y][x]]
    top, bot, left, right = ys[0], ys[-1], min(xs), max(xs)
    return [row[left:right + 1] for row in bm[top:bot + 1]]


def bitmap_from_pillow(path, index, px, thr, ch):
    """Pillow 原始渲染 → 裁到 ink 框（与 BDF 一致）。"""
    f = ImageFont.truetype(path, size=px * make_bdf.SUPERSAMPLE, index=index)
    rows = make_bdf.render_glyph(ch, px, f, thr)
    if rows is None:
        return None
    ys = [y for y in range(px) if any(rows[y][x] for x in range(px))]
    xs = [x for y in range(px) for x in range(px) if rows[y][x]]
    top, bot, left, right = ys[0], ys[-1], min(xs), max(xs)
    return [row[left:right + 1] for row in rows[top:bot + 1]]


def main():
    chars = make_bdf.collect_chars()
    allok = True
    for px, thr, build_mode in ((26, 110, 2), (28, 110, 2), (34, 110, 2)):
        print("== 雅黑 %dpx (thr=%d, build=%d) ==" % (px, thr, build_mode))
        try:
            data = make_font(MSYH[0], MSYH[1], px, thr, build_mode, chars)
        except RuntimeError as e:
            print("   生成失败: %s" % e)
            allok = False
            continue
        info = FontInfo(data)
        print("   v1 二进制 %d 字节, 表项 %d" % (len(data), info.glyph_cnt))
        bad = 0
        checked = 0
        for ch in PROBE:
            bm, adv = bitmap_from_decoder(data, info, ch)
            ref = bitmap_from_pillow(MSYH[0], MSYH[1], px, thr, ch)
            if bm is None or ref is None:
                continue
            checked += 1
            bm_ink = crop_to_ink(bm)
            if bm_ink != ref:
                bad += 1
                if bad <= 2:
                    print("   !! %r 不一致  解码 %dx%d  原始 %dx%d"
                          % (ch, len(bm_ink[0]), len(bm_ink),
                             len(ref[0]), len(ref)))
            if adv != px:
                print("   !! %r advance=%d（期望 %d，等宽假设被破坏）" % (ch, adv, px))
        print("   比对 %d 字，不一致 %d 个 → %s"
              % (checked, bad, "OK" if bad == 0 else "!! 有问题"))
        if bad:
            allok = False
        print()
    print("结论: %s" % ("全部通过 ✅" if allok else "存在差异 ❌"))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
