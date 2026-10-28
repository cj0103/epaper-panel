# -*- coding: utf-8 -*-
"""
字库流水线：Pillow 渲染 → BDF → 官方 bdfconv（-f 1 = u8g2 v1 格式）
→ 转换为本项目的 fonts_ink.cpp / fonts_ink.h。

**为什么用官方 bdfconv 而不是自研编码器**：
  v1 格式位流细节多（游程对编码、终止对、unicode 查找表、dy 约定、
  单字形 ≤255B 上限），自研编码器 + 自研仿真器互相验证会把同类错误
  互相掩盖（2026-10 踩坑两小时的根因）。bdfconv 是 u8g2 官方工具，
  产物与 U8g2_for_Adafruit_GFX v1.8.0 的解析器 100% 兼容。

依赖：tools/u8g2tools/bdfconv.exe（u8g2 官方 Windows 二进制）
"""
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from make_bdf import write_bdf, collect_chars   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
U8G2 = TOOLS / "u8g2tools"
WORK = U8G2 / "work"
OUT = ROOT / "firmware" / "epd_panel"
BDFCONV = U8G2 / "bdfconv.exe"

# 字号档 → (bdfconv build mode, 渲染阈值)
#  28/34px: 阈值 110（笔画饱满），build 2（统一字高）
#  44px:    阈值 180（只留笔画核心，避免 v1 单字形 >255B），
#           build 0（最小位图，进一步减小游程数）
# 2026-10-28 定档：雅黑 26/28/34（誊抄默认26可选档，课程表固定28）
# 全部阈值 110、build 2；雅黑 44px 因 v1 单字形 255B 上限不可行，已弃用
SIZES = {
    26: dict(build=2, threshold=110),
    28: dict(build=2, threshold=110),
    34: dict(build=2, threshold=110),
}

# 收录范围：ASCII 可打印 + CJK 统一表意 + GB2312 符号区 + 中文标点 + 全角
# $2000-$206f：中文弯引号“”‘’ 与省略号…
# $00b7,$00d7,$00f7：间隔号·、乘号×、除号÷（GB2312 里的特殊符号，
#   不在 a0a1-a1fe 段内，早前漏收）
MAP = ("$20-$7e,$4e00-$9fff,$a0a1-$a1fe,$2000-$206f,$3000-$303f,$ff00-$ffef,"
       "$00b7,$00d7,$00f7")


def run(cmd, **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return p


def bdfconv(bdf, out_c, build):
    """调用官方 bdfconv 生成 v1 格式字体。失败抛异常（含错误信息）。"""
    p = run([str(BDFCONV), "-f", "1", "-b", str(build), "-m", MAP,
             str(bdf), "-o", str(out_c)])
    text = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0 or "Error" in text:
        raise RuntimeError("bdfconv 失败:\n%s" % text[-2000:])
    return text


def emit_cpp(cpp_lines, h_lines, name, data):
    """把字体字节写成 C 数组（8 进制转义，u8g2 风格）。"""
    cpp_lines.append(
        'const uint8_t %s[%d] U8G2_FONT_SECTION("%s") =' % (name, len(data) + 1, name))
    chunk = []
    for i in range(0, len(data), 24):
        part = data[i:i + 24]
        chunk.append('  "' + "".join("\\%03o" % b for b in part) + '"')
    cpp_lines.append("\n".join(chunk) + ";")
    cpp_lines.append("")
    h_lines.append("extern const uint8_t %s[];" % name)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if not BDFCONV.exists():
        print("缺少 bdfconv.exe: %s" % BDFCONV)
        return 1

    # 可选：命令行指定只跑某几档，如 "python gen_fonts_v1.py 28"（用于单档试跑）
    only = None
    if len(sys.argv) > 1:
        only = {int(a) for a in sys.argv[1].split(",") if a.strip()}

    chars = collect_chars()
    print("字符集 %d (ASCII %d)" % (len(chars),
                                    sum(1 for c in chars if ord(c) < 128)))

    cpp = ["// 自动生成：u8g2 v1 中文字库（微软雅黑 26/28/34）by gen_fonts_v1.py",
           "// 由 u8g2 官方 bdfconv -f 1 生成，兼容 U8g2_for_Adafruit_GFX v1.8.0",
           '#include "fonts_ink.h"', "#include <u8g2_fonts.h>", ""]
    h = ["// 自动生成：u8g2 v1 中文字库声明（微软雅黑 26/28/34）",
         "#ifndef FONTS_INK_H", "#define FONTS_INK_H",
         "#include <stdint.h>", "",
         "// 每档字号一个字体，含 ASCII + GB2312 + CJK 统一表意 + 中文标点。",
         "// 字形宽度由 bdfconv 统一（build mode 见 gen_fonts_v1.py），",
         "// advance 宽度 = 字号（等宽），空格不入字库（渲染层按字号步进）。"]

    total = 0
    for px, cfg in SIZES.items():
        if only is not None and px not in only:
            # 单档试跑时保留已有字库数据，避免覆盖成不完整版本
            old = OUT / "fonts_ink.cpp"
            if old.exists():
                src = old.read_text(encoding="utf-8")
                import re as _re
                m = _re.search(r"const\s+uint8_t\s+%s\s*\[\s*\d+\s*\][^=]*?=\s*"
                               r"((?:\"[^\"]*\"\s*)+);" % ("msyh_%dpx" % px), src)
                if m:
                    data = _unescape_all(m.group(1))
                    emit_cpp(cpp, h, "msyh_%dpx" % px, data)
                    total += len(data) + 1
                    print("=== %dpx === (沿用已有字库)" % px, flush=True)
            continue
        bdf = WORK / ("msyh%d.bdf" % px)
        raw = WORK / ("raw%d.c" % px)
        print("=== %dpx ===" % px, flush=True)
        n, sk = write_bdf(str(bdf), chars, px, threshold=cfg["threshold"])
        print("  BDF %d 字形" % n, flush=True)
        bdfconv(bdf, raw, cfg["build"])
        # 解析 bdfconv 产物
        from parse_cfont import parse_c_font
        name, data, declared = parse_c_font(str(raw))
        print("  v1 字体 %d B (声明 %d)" % (len(data), declared), flush=True)
        emit_cpp(cpp, h, "msyh_%dpx" % px, data)
        total += len(data) + 1

    h += ["#endif", ""]
    (OUT / "fonts_ink.cpp").write_text("\n".join(cpp), encoding="utf-8")
    (OUT / "fonts_ink.h").write_text("\n".join(h), encoding="utf-8")
    print("done -> %s  字库总量 %.2f MB" % (OUT, total / 1048576.0))
    return 0


def _unescape_all(lit):
    """把 emit_cpp 生成的 C 字符串字面量还原成字节（用于单档试跑保留旧字库）。"""
    from parse_cfont import _unescape_c
    out = bytearray()
    pos = 0
    n = len(lit)
    while pos < n:
        ch = lit[pos]
        if ch.isspace():
            pos += 1
            continue
        if ch != '"':
            break
        j = pos + 1
        buf = []
        while j < n:
            c = lit[j]
            if c == "\\":
                buf.append(lit[j:j + 2])
                j += 2
                continue
            if c == '"':
                break
            buf.append(c)
            j += 1
        out.extend(_unescape_c("".join(buf)))
        pos = j + 1
    return bytes(out)


if __name__ == "__main__":
    sys.exit(main())
