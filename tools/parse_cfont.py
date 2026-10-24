# -*- coding: utf-8 -*-
"""解析 bdfconv 生成的 C 字体数组为原始字节 + 解析 v1 头。

bdfconv 输出的字符串字面量形如 "\\311\\2\\5..." —— 每个 \\NNN 是 3 位八进制
转义（\\NNN 十进制形式不会出现，全是八进制），需按 C 字符串字面量规则
解析（注意 \\\\ \\" 等转义）。

提供：
  parse_c_font(path) -> (name, bytes)
  parse_v1_header(data) -> dict
"""
import re
import sys


def _unescape_c(s):
    """解析 C 字符串字面量内容（已去掉外层引号）→ bytes"""
    out = bytearray()
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c != '\\':
            out.append(ord(c) & 0xFF)
            i += 1
            continue
        i += 1
        if i >= n:
            break
        e = s[i]
        if e in '01234567':
            # 八进制转义：最多 3 位
            j = i
            val = 0
            cnt = 0
            while j < n and cnt < 3 and s[j] in '01234567':
                val = val * 8 + int(s[j], 8)
                j += 1
                cnt += 1
            out.append(val & 0xFF)
            i = j
        else:
            mapping = {'n': 10, 't': 9, 'r': 13, 'a': 7, 'b': 8, 'f': 12,
                       'v': 11, '\\': 92, '"': 34, '?': 63, "'": 39}
            out.append(mapping.get(e, ord(e)))
            i += 1
    return bytes(out)


def parse_c_font(path):
    """从 .c 文件里提取第一个 uint8_t 数组 → (name, bytes)"""
    src = open(path, encoding='utf-8', errors='replace').read()
    # 注意：数组名后可能跟 U8G2_FONT_SECTION("name") 宏（内含带引号字符串），
    # 必须跳过宏参数再定位 '=' 后的字面量列表。
    m = re.search(r'const\s+uint8_t\s+(\w+)\s*\[\s*(\d+)\s*\][^=]*?=\s*',
                  src)
    if not m:
        raise ValueError('未找到字体数组: %s' % path)
    name, declared = m.group(1), int(m.group(2))
    rest = src[m.end():]
    # 字面量里可能出现裸 ';'（如 "\377;"），不能用 find(';') 定位结尾。
    # 改为：按 C 字符串字面量规则扫描，把连续字面量全部取出，
    # 遇到非引号非空白字符即停。
    data = bytearray()
    pos = 0
    n = len(rest)
    while pos < n:
        ch = rest[pos]
        if ch.isspace():
            pos += 1
            continue
        if ch != '"':
            break
        # 扫描一个字面量
        j = pos + 1
        buf = []
        while j < n:
            c = rest[j]
            if c == '\\':
                buf.append(rest[j:j + 2])
                j += 2
                continue
            if c == '"':
                break
            buf.append(c)
            j += 1
        data.extend(_unescape_c(''.join(buf)))
        pos = j + 1
    return name, bytes(data), declared


def parse_v1_header(d):
    """解析 u8g2 v1 字体头（23 字节）"""
    if len(d) < 23:
        raise ValueError('数据不足 23 字节')
    return dict(
        glyph_cnt=d[0], bbx_mode=d[1],
        bits_per_0=d[2], bits_per_1=d[3],
        bits_per_char_width=d[4], bits_per_char_height=d[5],
        bits_per_char_x=d[6], bits_per_char_y=d[7], bits_per_delta_x=d[8],
        max_char_width=d[9], max_char_height=d[10],
        x_offset=d[11], y_offset=d[12],
        ascent_A=d[13], descent_g=d[14],
        ascent_para=d[15], descent_para=d[16],
        start_pos_upper_A=(d[17] << 8) | d[18],
        start_pos_lower_a=(d[19] << 8) | d[20],
        start_pos_unicode=(d[21] << 8) | d[22],
    )


if __name__ == '__main__':
    for p in sys.argv[1:]:
        name, data, declared = parse_c_font(p)
        h = parse_v1_header(data)
        print('%s: name=%s declared=%d actual=%d' %
              (p, name, declared, len(data)))
        print('  hdr:', ' '.join('%02x' % b for b in data[:23]))
        for k, v in h.items():
            print('   ', k, '=', v)
