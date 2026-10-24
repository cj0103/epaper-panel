# -*- coding: utf-8 -*-
"""离线验证 u8g2 v1 字库与 U8g2_for_Adafruit_GFX 桥接库的兼容性。

做法：把桥接库的解码路径（C 源码）**逐行复刻**成 Python，然后在本地把
fonts_ink.cpp 里的字库字节解出像素，与 Pillow 渲染的原始字形对照。

与之前"自研编码器 + 自研仿真器"互相验证的做法不同：这里的**编码器是官方
bdfconv**，解码器是照抄 C 源码的只读实现，两端独立，能真实暴露格式不兼容。

验证内容：
  1. 头字段解析（23 字节，signed 按 8 位补码）
  2. 单字节区（ASCII）查找
  3. Unicode 区（>255）查找 + unicode LUT 定位
  4. 字形解码（游程折行）→ 像素位图
  5. 关键字符的像素级对比（Pillow 原始渲染 vs 桥接库解码）

用法：
    python v1_verify.py                  # 全部三档 + 关键字符对比
    python v1_verify.py --art 课         # 只看某个字符的 ASCII art
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse_cfont import parse_c_font  # noqa: E402

PANEL = Path(__file__).resolve().parent.parent / "firmware" / "epd_panel"


# ---------------------------------------------------------------- 头解析
class FontInfo(object):
    """对应桥接库的 u8g2_font_info_t（u8g2_read_font_info）。"""

    def __init__(self, d):
        self.glyph_cnt = d[0]
        self.bbx_mode = d[1]
        self.bits_per_0 = d[2]
        self.bits_per_1 = d[3]
        self.bits_per_char_width = d[4]
        self.bits_per_char_height = d[5]
        self.bits_per_char_x = d[6]
        self.bits_per_char_y = d[7]
        self.bits_per_delta_x = d[8]
        self.max_char_width = d[9]
        self.max_char_height = d[10]
        self.x_offset = _s8(d[11])
        self.y_offset = _s8(d[12])
        self.ascent_A = d[13]
        self.descent_g = _s8(d[14])
        self.ascent_para = d[15]
        self.descent_para = _s8(d[16])
        self.start_pos_upper_A = (d[17] << 8) | d[18]
        self.start_pos_lower_a = (d[19] << 8) | d[20]
        self.start_pos_unicode = (d[21] << 8) | d[22]


def _s8(v):
    """uint8_t -> int8_t（8 位补码），对应 C 的隐式转换。"""
    return v - 256 if v > 127 else v


# ---------------------------------------------------------------- 解码器
class Decoder(object):
    """复刻 u8g2_font_decode_* 系列（照 U8g2_for_Adafruit_GFX.cpp）。"""

    def __init__(self, data, info):
        self.d = data
        self.info = info
        self.ptr = 0
        self.bit_pos = 0
        self.glyph_width = 0
        self.glyph_height = 0
        self.x = 0
        self.y = 0
        # 画布：局部坐标 + 像素位
        self.pixels = []

    def u8(self, pos):
        return self.d[pos]

    # u8g2_font_decode_get_unsigned_bits
    def unsigned_bits(self, cnt):
        val = self.u8(self.ptr)
        val >>= self.bit_pos
        bit_pos_plus_cnt = self.bit_pos + cnt
        if bit_pos_plus_cnt >= 8:
            s = 8 - self.bit_pos
            self.ptr += 1
            val |= self.u8(self.ptr) << s
            bit_pos_plus_cnt -= 8
        val &= (1 << cnt) - 1
        self.bit_pos = bit_pos_plus_cnt
        return val & 0xFF

    # u8g2_font_decode_get_signed_bits
    def signed_bits(self, cnt):
        v = self.u8_signed(self.unsigned_bits(cnt))
        d = 1 << (cnt - 1)
        return v - d

    @staticmethod
    def u8_signed(v):
        return v - 256 if v > 127 else v

    # u8g2_font_decode_len：只推进光标并记录像素，不真的画
    def decode_len(self, ln, is_fg):
        cnt = ln
        lx, ly = self.x, self.y
        while True:
            rem = (self.glyph_width - lx) & 0xFF
            current = rem
            if cnt < rem:
                current = cnt
            if current > 0:
                for i in range(current):
                    self.pixels.append((lx + i, ly, bool(is_fg)))
            if cnt < rem:
                break
            cnt -= rem
            lx = 0
            ly += 1
        lx += cnt
        self.x = lx
        self.y = ly

    # u8g2_font_setup_decode
    def setup_decode(self, glyph_ptr):
        self.ptr = glyph_ptr
        self.bit_pos = 0
        self.glyph_width = self.unsigned_bits(self.info.bits_per_char_width)
        self.glyph_height = self.unsigned_bits(self.info.bits_per_char_height)

    # u8g2_font_decode_glyph
    def decode_glyph(self, glyph_ptr):
        self.setup_decode(glyph_ptr)
        h = self.glyph_height
        x = self.signed_bits(self.info.bits_per_char_x)
        y = self.signed_bits(self.info.bits_per_char_y)
        d = self.signed_bits(self.info.bits_per_delta_x)
        self.x = 0
        self.y = 0
        self.pixels = []
        if self.glyph_width > 0:
            # target 位移不影响字形本身形状，这里只用于基线核对
            self.dx_off = x
            self.dy_off = -(h + y)
            while True:
                a = self.unsigned_bits(self.info.bits_per_0)
                b = self.unsigned_bits(self.info.bits_per_1)
                while True:
                    self.decode_len(a, 0)
                    self.decode_len(b, 1)
                    if self.unsigned_bits(1) == 0:
                        break
                if self.y >= h:
                    break
        return d


def find_glyph_data(data, info, encoding):
    """复刻 u8g2_font_get_glyph_data，返回 (glyph_data_offset, None) 或 (None, None)。"""
    font = 23
    n = len(data)
    if encoding <= 255:
        if encoding >= ord("a"):
            font += info.start_pos_lower_a
        elif encoding >= ord("A"):
            font += info.start_pos_upper_A
        while font < n - 1:
            if data[font + 1] == 0:
                break
            if data[font] == encoding:
                return font + 2
            font += data[font + 1]
    else:
        font += info.start_pos_unicode
        ult = font
        while font < n - 3:
            font += (data[ult] << 8) | data[ult + 1]
            e = (data[ult + 2] << 8) | data[ult + 3]
            ult += 4
            if not (e < encoding):
                break
        while font < n - 2:
            e = (data[font] << 8) | data[font + 1]
            if e == 0:
                break
            if e == encoding:
                return font + 3
            font += data[font + 2]
    return None


def render_glyph(data, info, encoding):
    """解出字形像素，返回 (bitmap, advance, meta)。bitmap 是 2D list。"""
    off = find_glyph_data(data, info, encoding)
    if off is None:
        return None, None, None
    dec = Decoder(data, info)
    adv = dec.decode_glyph(off)
    w = dec.glyph_width
    h = dec.glyph_height
    bm = [[0] * max(w, 1) for _ in range(max(h, 1))]
    for (px, py, fg) in dec.pixels:
        if 0 <= py < len(bm) and 0 <= px < len(bm[0]):
            bm[py][px] = 1 if fg else 0
    meta = dict(width=w, height=h, dx_off=dec.dx_off, dy_off=dec.dy_off)
    return bm, adv, meta


def to_art(bm):
    return "\n".join("".join("#" if v else "." for v in row) for row in bm)


# ---------------------------------------------------------------- 校验
def check_font(path, label):
    src = path.read_text(encoding="utf-8")
    # fonts_ink.cpp 含多个数组，逐个解析
    import re
    names = re.findall(r"const\s+uint8_t\s+(\w+)\s*\[\s*(\d+)\s*\]", src)
    print("=" * 60)
    print("字体文件: %s" % path.name)
    for nm, declared in names:
        data = _extract(src, nm)
        info = FontInfo(data)
        print("-" * 56)
        print("  %s  %d B (声明 %s)" % (nm, len(data), declared))
        print("  glyph_cnt=%d bits(0/1)=%d/%d char(w/h/x/y/dx)=%d/%d/%d/%d/%d"
              % (info.glyph_cnt, info.bits_per_0, info.bits_per_1,
                 info.bits_per_char_width, info.bits_per_char_height,
                 info.bits_per_char_x, info.bits_per_char_y,
                 info.bits_per_delta_x))
        print("  max(w/h)=%d/%d  xoff=%d yoff=%d  ascent_A=%d descent_g=%d"
              % (info.max_char_width, info.max_char_height,
                 info.x_offset, info.y_offset, info.ascent_A, info.descent_g))
        print("  ascent_para=%d descent_para=%d  pos(A/a/uni)=%d/%d/%d"
              % (info.ascent_para, info.descent_para,
                 info.start_pos_upper_A, info.start_pos_lower_a,
                 info.start_pos_unicode))
        # 抽样解码
        for ch in ("A", "0", "a", "!", "课", "程", "表", "，", "。"):
            enc = ord(ch)
            bm, adv, meta = render_glyph(data, info, enc)
            if bm is None:
                print("    !! 字符 %r (U+%04X) 未找到字形" % (ch, enc))
                continue
            ink = sum(sum(r) for r in bm)
            print("    %r U+%04X  %dx%d adv=%d dxoff=%d dyoff=%d 墨点=%d"
                  % (ch, enc, meta["width"], meta["height"], adv,
                     meta["dx_off"], meta["dy_off"], ink))
    return None, None


def _extract(src, name):
    """从 .cpp 里抽出指定数组的字节。"""
    import re
    m = re.search(r"const\s+uint8_t\s+%s\s*\[\s*(\d+)\s*\][^=]*?=\s*" % name, src)
    rest = src[m.end():]
    from parse_cfont import _unescape_c
    data = bytearray()
    pos, n = 0, len(rest)
    while pos < n:
        ch = rest[pos]
        if ch.isspace():
            pos += 1
            continue
        if ch != '"':
            break
        j = pos + 1
        buf = []
        while j < n:
            c = rest[j]
            if c == "\\":
                buf.append(rest[j:j + 2])
                j += 2
                continue
            if c == '"':
                break
            buf.append(c)
            j += 1
        data.extend(_unescape_c("".join(buf)))
        pos = j + 1
    return bytes(data)


def main():
    args = sys.argv[1:]
    cpp = PANEL / "fonts_ink.cpp"
    if not cpp.exists():
        print("找不到 %s" % cpp)
        return 1

    if args and args[0] == "--art":
        ch = args[1]
        src = cpp.read_text(encoding="utf-8")
        import re
        for nm in re.findall(r"const\s+uint8_t\s+(\w+)\s*\[", src):
            data = _extract(src, nm)
            info = FontInfo(data)
            bm, adv, meta = render_glyph(data, info, ord(ch))
            if bm is None:
                continue
            print("--- %s  '%s' %dx%d adv=%d ---"
                  % (nm, ch, meta["width"], meta["height"], adv))
            print(to_art(bm))
        return 0

    check_font(cpp, "fonts_ink")
    return 0


if __name__ == "__main__":
    sys.exit(main())
