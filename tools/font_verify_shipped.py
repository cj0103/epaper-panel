# -*- coding: utf-8 -*-
"""
校验**固件实际产物** fonts_ink.cpp 里的字库（不是重新生成的小样本）：
  1. 从 fonts_ink.cpp 提取各档字体二进制
  2. v1_verify.Decoder（固件同款解析器）抽样解码
  3. 与 Pillow 原始渲染（同一 FONT_FILE/阈值）像素级比对（裁墨迹框）
  4. 校验 advance == 字号（等宽假设）

用法：
  E:\\software\\python311\\python.exe tools\\font_verify_shipped.py
"""
import sys
from pathlib import Path

from PIL import ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_bdf
from parse_cfont import parse_c_font
from v1_verify import FontInfo, Decoder, _extract, find_glyph_data
from font_decode_check import crop_to_ink, bitmap_from_pillow, PROBE

ROOT = Path(__file__).resolve().parent.parent
CPP = ROOT / "firmware" / "epd_panel" / "fonts_ink.cpp"
FONT_FILE = make_bdf.FONT_FILE   # ★ 与字库生成用同一字体文件，防止口径漂移


def main():
    src = CPP.read_text(encoding="utf-8")
    allok = True
    pxs = (26, 28, 34)
    for px in pxs:
        name = "msyh_%dpx" % px
        try:
            data = _extract(src, name)
        except Exception as e:                     # noqa: BLE001
            print("== %s == 提取失败: %s" % (name, e))
            allok = False
            continue
        info = FontInfo(data)
        print("== %s == v1 二进制 %d 字节, 表项 %d" % (name, len(data), info.glyph_cnt))
        f = ImageFont.truetype(FONT_FILE, size=px * make_bdf.SUPERSAMPLE, index=0)
        bad = checked = 0
        for ch in PROBE:
            off = find_glyph_data(data, info, ord(ch))
            if off is None:
                print("   !! %r 字形缺失" % ch)
                bad += 1
                continue
            dec = Decoder(data, info)
            adv = dec.decode_glyph(off)
            bm = [[0] * dec.glyph_width for _ in range(dec.glyph_height)]
            for (lx, ly, is_fg) in dec.pixels:
                if 0 <= ly < dec.glyph_height and 0 <= lx < dec.glyph_width:
                    bm[ly][lx] = 1 if is_fg else 0
            ref = bitmap_from_pillow(FONT_FILE, 0, px, make_bdf.THRESHOLD, ch)
            ink = crop_to_ink(bm)
            checked += 1
            if ink != ref:
                bad += 1
                if bad <= 2:
                    print("   !! %r 不一致 解码 %s 原始 %s"
                          % (ch, None if ink is None else (len(ink[0]), len(ink)),
                             None if ref is None else (len(ref[0]), len(ref))))
            if adv != px:
                print("   !! %r advance=%d (期望 %d)" % (ch, adv, px))
                bad += 1
        print("   比对 %d 字, 不一致 %d -> %s" % (checked, bad, "OK" if not bad else "!!"))
        if bad:
            allok = False
    print("结论: %s (字体文件=%s)" % ("全部通过" if allok else "存在差异", FONT_FILE))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
