# -*- coding: utf-8 -*-
"""
BDF 生成器（Pillow 渲染 → BDF 文本）——为 u8g2 官方 bdfconv 准备输入。

为什么不自己写 u8g2 v1 编码器：
  v1 字体的位流格式（游程对、terminate 对、unicode 查找表、dy 约定）
  细节极多且桥接库解析器是硬编码的——自研编码器 + 自研仿真器互相验证
  会把同类错误互相掩盖（本次踩坑根源）。官方 bdfconv -f 1 输出的字体
  是 u8g2 自身在用的，必然与桥接库 v1.8.0 兼容。

BDF 格式要点（bdfconv 需要）：
  STARTFONT 2.1
  FONT <name>
  SIZE <pt> <xres> <yres>
  FONTBOUNDINGBOX <w> <h> <xoff> <yoff>
  STARTPROPERTIES n / FONT_ASCENT / FONT_DESCENT / ENDPROPERTIES
  CHARS n
  STARTCHAR <name>
  ENCODING <code>
  SWIDTH <scale> 0
  DWIDTH <w> 0
  BBX <w> <h> <xoff> <yoff>
  BITMAP
  <每行 ceil(w/8) 个十六进制字节，大写，2位/字节>
  ENDCHAR
  ENDFONT

渲染策略（关键，避免直接栅格化出碎形）：
  Pillow 12.1 + simhei 在小字号直接栅格化会碎（bitmap strike 质量差）。
  解法：size = px*4 超采样渲染 → LANCZOS 缩回 px → 阈值二值化。
  另需外扩留白（pad），防 LANCZOS 负振铃切掉贴边像素行。
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT_FILE = r"C:\Windows\Fonts\simhei.ttf"
SUPERSAMPLE = 4
THRESHOLD = 110
# 可调阈值：大字号（44px）单字形墨量过高会让 v1 RLE 压缩超过 255B 上限，
# 提高阈值只保留笔画核心（去掉抗锯齿边缘）→ 游程更短 → 可编码。
# 128=标准，160=偏瘦（44px 用），110=偏胖（28/34px 用）。
THRESHOLD_OVERRIDE = None

_FONTS = {}


def get_font(px):
    """4x 超采样字体（缓存）。"""
    if px not in _FONTS:
        _FONTS[px] = ImageFont.truetype(FONT_FILE, size=px * SUPERSAMPLE)
    return _FONTS[px]


def render_glyph(ch, px, font=None, threshold=None):
    """渲染单个字符为 px×px 二值点阵（0/1 的 list[list[int]]）。
    空白字符返回 None（不入字库，渲染层按字号步进补位）。"""
    font = font or get_font(px)
    thr = THRESHOLD if threshold is None else threshold
    scale = SUPERSAMPLE
    big = px * scale
    pad = 6 * scale
    img = Image.new("L", (big + 2 * pad, big + 2 * pad), 0)
    d = ImageDraw.Draw(img)
    # anchor="mm" 以画布中心对中 → 字形落在整格中央
    d.text((pad + big // 2, pad + big // 2), ch, fill=255, font=font, anchor="mm")
    img = img.resize(((big + 2 * pad) // scale, (big + 2 * pad) // scale),
                     Image.LANCZOS)
    img = img.crop((pad // scale, pad // scale,
                    pad // scale + px, pad // scale + px))
    data = img.load()
    rows = [[1 if data[x, y] > thr else 0 for x in range(px)]
            for y in range(px)]
    if not any(any(r) for r in rows):
        return None
    return rows


def _bbox(rows, px):
    """ink 包围盒：top/bottom 行、left/right 列、全墨与否"""
    ys = [y for y in range(px) if any(rows[y][x] for x in range(px))]
    xs = [x for y in range(px) for x in range(px) if rows[y][x]]
    if not ys:
        return None
    return ys[0], ys[-1], min(xs), max(xs)


def baseline_row(px, font=None):
    """真实基线在 cell 内的行号（与 _hex_rows 输出同坐标系，0-based）。

    渲染用 anchor='mm'：Pillow 把「ascender 与 descender 的中点」对齐到锚点 y，
    即（4x 坐标）baseline_sup = anchor_y + (asc - desc) / 2。
    LANCZOS 缩回 px 后再裁掉 pad，得到 cell 内的基线行号。

    【坑·已修】早前这里错用 px-1 当基线，且 yoff 符号取反：
        "yoff": -(px - 1 - bot)     ← 双重错误
    结果每个字的垂直偏移被镜像：满格字（课/周/四）误差小所以看着正常，
    而墨迹只占格中部的字（一/二/三/五）被整体下移 8~20px——
    「一」沉到基线下方 12px，被下一行的白色背景矩形整条擦掉（曾导致"一"字消失）。
    """
    font = font or get_font(px)
    scale = SUPERSAMPLE
    big = px * scale
    pad = 6 * scale
    asc, desc = font.getmetrics()
    anchor_y = pad + big // 2
    baseline_sup = anchor_y + (asc - desc) / 2.0
    return baseline_sup / scale - pad / scale


def _hex_rows(rows, w, x0):
    """按 BDF BITMAP 格式输出：每行 ceil(w/8) 字节，大写十六进制。
    位序：MSB 在左（BDF 规范，与 u8g2 内部解码的位序无关，
    bdfconv 负责转成 v1 位流）。"""
    out = []
    nbytes = (w + 7) // 8
    for r in rows:
        line = []
        for b in range(nbytes):
            v = 0
            for bit in range(8):
                col = b * 8 + bit
                if col < w and r[x0 + col]:
                    v |= 0x80 >> bit
            line.append("%02X" % v)
        out.append("".join(line))
    return out


def write_bdf(path, chars, px, font=None, threshold=None):
    """生成 BDF 文件。chars：待收录字符列表（str 元素）。
    返回 (收录数, 跳过数)。"""
    font = font or get_font(px)
    base = int(round(baseline_row(px, font)))
    glyphs = []
    skipped = 0
    for ch in chars:
        rows = render_glyph(ch, px, font, threshold)
        if rows is None:
            skipped += 1
            continue
        bb = _bbox(rows, px)
        if bb is None:
            skipped += 1
            continue
        top, bot, left, right = bb
        gw = right - left + 1
        gh = bot - top + 1
        # 裁到 ink 框（BBX 相对基线：yoff 为负表示向下）
        sub = [rows[y][left:right + 1] for y in range(top, bot + 1)]
        # 【关键】yoff = 基线行 - ink 底行，正数 = ink 在基线上方。
        # BDF 的 yoff 约定：正值向上、负值向下。早前写成 -(px-1-bot)
        # 既用错了基线又把符号取反，导致「一/二/三/五」整体下沉（详见 baseline_row 注释）。
        glyphs.append({
            "ch": ch, "enc": ord(ch), "rows": sub,
            "w": gw, "h": gh, "xoff": left, "yoff": base - bot,
        })

    if not glyphs:
        raise RuntimeError("无有效字形")

    # 全局 FONT_ASCENT / FONT_DESCENT：按**真实基线**算，而不是 ink 框高度。
    # ascent = ink 最高点相对基线向上多少；descent = ink 最低点向下多少。
    ascent = max(g["yoff"] + g["h"] - 1 for g in glyphs)
    descent = max(-g["yoff"] for g in glyphs)

    lines = []
    lines.append("STARTFONT 2.1")
    lines.append("FONT simhei-%dpx" % px)
    lines.append("SIZE %d 75 75" % px)
    lines.append("FONTBOUNDINGBOX %d %d 0 %d" % (px, ascent + descent, -descent))
    lines.append("STARTPROPERTIES 2")
    lines.append("FONT_ASCENT %d" % ascent)
    lines.append("FONT_DESCENT %d" % descent)
    lines.append("ENDPROPERTIES")
    lines.append("CHARS %d" % len(glyphs))
    for g in glyphs:
        name = g["ch"] if g["ch"].strip() else "uni%04X" % g["enc"]
        lines.append("STARTCHAR %s" % name)
        lines.append("ENCODING %d" % g["enc"])
        lines.append("SWIDTH %d 0" % (px * 1000 // 8))
        lines.append("DWIDTH %d 0" % px)
        lines.append("BBX %d %d %d %d" % (g["w"], g["h"], g["xoff"], g["yoff"]))
        lines.append("BITMAP")
        lines.extend(_hex_rows(g["rows"], g["w"], 0))
        lines.append("ENDCHAR")
    lines.append("ENDFONT")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(glyphs), skipped


def collect_chars(wide=True, ascii_only=False):
    """字符集：ASCII 可打印 + GB2312 全集 + 常用符号。"""
    chars = set()
    for c in range(0x21, 0x7F):
        chars.add(chr(c))
    if not ascii_only:
        for hi in range(0xB0, 0xF8):
            for lo in range(0xA1, 0xFF):
                try:
                    chars.add(bytes([hi, lo]).decode("gb2312"))
                except UnicodeDecodeError:
                    pass
        chars.update("，。！？；：、“”‘’（）【】《》—…·～￥×÷")
    return sorted(chars, key=ord)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "simhei.bdf"
    px = int(sys.argv[2]) if len(sys.argv) > 2 else 28
    thr = int(sys.argv[3]) if len(sys.argv) > 3 else None
    n, sk = write_bdf(out, collect_chars(), px, threshold=thr)
    print("BDF %s: %d 字形, 跳过 %d, 阈值 %s" %
          (out, n, sk, thr if thr is not None else THRESHOLD))
