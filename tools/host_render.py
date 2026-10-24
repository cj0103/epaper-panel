# -*- coding: utf-8 -*-
"""主机端渲染预览：复刻 epd_panel 渲染层，在电脑上出 PNG 再烧录。

用途：改完字库/布局先在电脑上看像素级效果，确认无误再编译烧录，
避免"烧一次刷一次"的低效试错。

与实机的一致性保障：
  - 解码器 = v1_verify（逐行复刻 U8g2_for_Adafruit_GFX 的 C 源码）
  - 坐标语义 = render_panel.cpp 的同一套常量
  - 透明模式 = 只画墨点不画背景矩形（与 setFontMode(1) 一致）

用法：
    python host_render.py --timetable              # 默认课程表样例
    python host_render.py --timetable "周一：语文、数学"   # 自定义（用 \n 分行）
    python host_render.py --scribe                 # 誊抄页
    python host_render.py "我和哪吒过一天" 28        # 单行文本
"""
import sys
from pathlib import Path

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:          # 没有 Pillow 时退化为 ASCII 输出
    HAVE_PIL = False

sys.path.insert(0, str(Path(__file__).parent))
from v1_verify import Decoder, FontInfo, _extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CPP = ROOT / "firmware" / "epd_panel" / "fonts_ink.cpp"

PANEL_W, PANEL_H = 480, 800

# 颜色（与 GxEPD2 一致：黑=0 白=255 红=需在 1-bit 屏上单独标注）
BLACK, WHITE = 0, 255
RED_MARK = 1   # 伪彩色标记（PNG 里用深红表示，1-bit 屏上会是纯黑）


class Font(object):
    def __init__(self, name):
        src = CPP.read_text(encoding="utf-8")
        self.name = name
        self.data = _extract(src, name)
        self.info = FontInfo(self.data)

    def decode(self, ch):
        """返回 (pixels, adv, meta)；pixels 是 [(lx, ly, is_fg)] 局部坐标。"""
        from v1_verify import find_glyph_data
        enc = ord(ch)
        off = find_glyph_data(self.data, self.info, enc)
        if off is None:
            return None, 0, None
        dec = Decoder(self.data, self.info)
        adv = dec.decode_glyph(off)
        meta = dict(width=dec.glyph_width, height=dec.glyph_height,
                    dx_off=dec.dx_off, dy_off=dec.dy_off)
        return dec.pixels, adv, meta


class Canvas(object):
    """1-bit 画布，坐标即逻辑像素。"""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.bits = bytearray(w * h)
        self.red = bytearray(w * h)     # 红字标记（1-bit 屏上不可区分，预览用）
        if HAVE_PIL:
            self.img = Image.new("L", (w, h), 255)
            self.px = self.img.load()

    def dot(self, x, y, on=True, red=False):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.bits[y * self.w + x] = 1 if on else 0
            if red:
                self.red[y * self.w + x] = 1
            if HAVE_PIL:
                self.px[x, y] = 0 if on else 255

    def hline(self, x0, x1, y):
        for x in range(int(x0), int(x1) + 1):
            self.dot(x, y)

    def ascii(self, x0=0, y0=0, x1=None, y1=None):
        x1 = self.w if x1 is None else x1
        y1 = self.h if y1 is None else y1
        out = []
        for y in range(int(y0), int(y1)):
            row = "".join("#" if self.bits[y * self.w + x] else "."
                          for x in range(int(x0), int(x1)))
            out.append(row)
        return "\n".join(out)

    def save(self, path, scale=2):
        if HAVE_PIL:
            img = self.img
            if any(self.red):
                # 红字用深红叠加，直观看得出哪行是红色天标题
                rgb = Image.merge("RGB", (img, img, img)).convert("RGB")
                px = rgb.load()
                for y in range(self.h):
                    for x in range(self.w):
                        if self.red[y * self.w + x] and self.bits[y * self.w + x]:
                            px[x, y] = (150, 20, 20)
                img = rgb
            img = img.resize((self.w * scale, self.h * scale), Image.NEAREST)
            img.save(path)
            print("saved:", path)
        else:
            print(self.ascii())


def draw_text_at(cv, font, x, y, text, px, red=False):
    """复刻 render_panel.cpp 的 drawTextAt（空格按 px 步进，字按 advance 步进）。

    桥接库在透明模式（setFontMode(1)）下不画背景矩形，只画前景墨迹。
    """
    out = []
    for ch in text:
        if ch == " ":
            x += px
            out.append((ch, None, x))
            continue
        pixels, adv, meta = font.decode(ch)
        if pixels is None:
            x += px
            out.append((ch, None, x))
            continue
        tx = x + meta["dx_off"]
        ty = y + meta["dy_off"]
        for (lx, ly, fg) in pixels:
            if fg:
                cv.dot(tx + lx, ty + ly, red=red)
        x += adv          # u8g2 内部 advance 步进
        out.append((ch, meta, x))
    return x, out


def text_w(text, px):
    """复刻 render_panel.cpp 的 textW（advance 恒等于字号，逐字累加）。"""
    return len(text) * px


def wrap(s, max_cols):
    """复刻 render_panel.cpp wrapLines（按可用列数断行）。"""
    out, cur, cnt = [], "", 0
    for ch in s:
        if cnt >= max_cols:
            out.append(cur)
            cur, cnt = "", 0
        cur += ch
        cnt += 1
    if cnt:
        out.append(cur)
    return out


def is_sep(ch):
    """全角「、」或半角逗号 = 断行优先点。"""
    return ch in "、,"


def wrap_seg(s, max_cols):
    """复刻 render_panel.cpp wrapSeg：按「、」边界断行，原子超长则硬切。"""
    atoms, buf = [], ""
    for ch in s:
        buf += ch
        if is_sep(ch):
            atoms.append(buf)
            buf = ""
    if buf:
        atoms.append(buf)
    out, cur, cnt = [], "", 0
    for atom in atoms:
        a = len(atom)
        if cnt > 0 and cnt + a > max_cols:
            out.append(cur)
            cur, cnt = "", 0
        if cnt == 0 and a > max_cols:
            for ch in atom:
                cur += ch
                cnt += 1
                if cnt >= max_cols:
                    out.append(cur)
                    cur, cnt = "", 0
        else:
            cur += atom
            cnt += a
    if cnt > 0:
        out.append(cur)
    return out


# ---------------- 课程表（复刻 render_panel.cpp drawTimetable） ----------------
# 真实课表样例（用户 2026-10-24 提供）：每天分上午/下午两段
DEFAULT_TT = [
    ("周一", [("上午", "语文、语文、数学、英语"),
              ("下午", "阅读、体育与健康、音乐、信息技术")]),
    ("周二", [("上午", "数学、语文、语文、科学"),
              ("下午", "十分钟队会、美术、美术、游泳")]),
    ("周三", [("上午", "数学、语文、人工智能、体育与健康"),
              ("下午", "专题教育、科学、体育活动、劳动")]),
    ("周四", [("上午", "体育与健康、语文、语文、数学"),
              ("下午", "红领巾广播、英语、道德与法治、音乐")]),
    ("周五", [("上午", "语文、体育与健康、书法、数学"),
              ("下午", "阅读、校本活动、英语、综合实践 (JA)")]),
]


def render_timetable(days, title="四 1 班课程表（游泳周）", out="课程表"):
    margin, px, lineH = 16, 28, 30
    titleBaseline, sepY, firstLine = 42, 54, 82
    footY = PANEL_H - 14
    lastLineFoot = footY - 40
    lastLineFull = PANEL_H - 12
    maxCols = (PANEL_W - 2 * margin) // px

    cv = Canvas(PANEL_W, PANEL_H)
    f28, f34 = Font("zhhei_28px"), Font("zhhei_34px")

    # 每段全文 + 行数（天标题独占一行 -> 每天 = 1 + 段行数）
    segs, dayLines = [], []
    for name, parts in days:
        daySegs = []
        for label, body in parts:
            full = (label + "：") if label else ""
            full += body
            daySegs.append(wrap_seg(full, maxCols))
        segs.append(daySegs)
        dayLines.append(1 + sum(len(x) for x in daySegs))

    # 单页时省掉页脚，多腾 1 行余量
    totalLines = sum(dayLines)
    maxLinesFull = (lastLineFull - firstLine) // lineH + 1
    maxLinesFoot = (lastLineFoot - firstLine) // lineH + 1
    singlePage = totalLines <= maxLinesFull
    lastLine = lastLineFull if singlePage else lastLineFoot
    maxLinesPerPage = maxLinesFull if singlePage else maxLinesFoot
    pageFirst, pageDays = [], []
    pg, used = 0, 0
    for d in range(len(days)):
        if used > 0 and used + dayLines[d] > maxLinesPerPage:
            pg += 1
            used = 0
        if pg >= len(pageDays):
            pageFirst.append(d)
            pageDays.append(0)
        pageDays[pg] += 1
        used += dayLines[d]
    pages = pg + 1
    print("days=%d cols=%d linesPerPage=%d pages=%d 每天行数=%s 合计=%d"
          % (len(days), maxCols, maxLinesPerPage, pages, dayLines, sum(dayLines)))

    page = 0
    d0 = pageFirst[page]
    d1 = d0 + pageDays[page] - 1

    # 标题（过长降 28px）
    tpx = 34
    if text_w(title, 34) > PANEL_W - 2 * margin:
        tpx = 28
    ftitle = f34 if tpx == 34 else f28
    draw_text_at(cv, ftitle, (PANEL_W - text_w(title, tpx)) // 2, titleBaseline, title, tpx)
    cv.hline(margin, PANEL_W - margin, sepY)

    # 正文：天标题独占一行（红），段内容顶格
    y = firstLine
    for d in range(d0, d1 + 1):
        if y > lastLine:
            break
        name, _ = days[d]
        draw_text_at(cv, f28, margin, y, name, 28, red=True)
        y += lineH
        for ls in segs[d]:
            for ln in ls:
                if y > lastLine:
                    break
                draw_text_at(cv, f28, margin, y, ln, 28)
                y += lineH

    if pages > 1:                      # 单页不画页脚
        draw_text_at(cv, f28, 14, footY, out, 28)
        w = text_w("%d/%d" % (page + 1, pages), 28)
        draw_text_at(cv, f28, PANEL_W - 14 - w, footY, "%d/%d" % (page + 1, pages), 28)
    return cv


# ---------------- 誊抄（复刻 render_panel.cpp drawScribe） ----------------
# 行首禁则标点（Unicode 码点）
NO_LINE_START_CP = set([
    0x3001, 0x3002, 0xFF0C, 0xFF01, 0xFF1F, 0xFF1B, 0xFF1A,
    0x201D, 0x2019, 0x300B, 0x300D, 0xFF09, 0x3011, 0x2026,
    0x002C, 0x002E, 0xFF0E,
])


def build_rows(text, cols):
    """复刻 scribeBuildRows：切行，返回每行起始字符下标列表 + 结束标记。

    规则：'\\n' 段落换行立即结束本行；'\\r' 忽略；
    行首禁则标点 -> 把上一行最后一个字挤到下一行（追い出し）。
    """
    chars = list(text)
    total = len(chars)
    rows = [0]
    row, ci, col = 0, 0, 0
    while ci < total and row < 339:
        ch = chars[ci]
        if ch == "\r":
            ci += 1
            continue
        if ch == "\n":
            ci += 1
            row += 1
            rows.append(ci)
            col = 0
            continue
        if col >= cols:
            if col > 0 and ci > 0 and ord(ch) in NO_LINE_START_CP:
                ci -= 1                      # 禁则：上一字挤到下一行
                row += 1
                rows.append(ci)
                col = 0
                continue
            row += 1
            rows.append(ci)
            col = 0
        ci += 1
        col += 1
    rows.append(total)
    return rows


def render_scribe(title="我和哪吒过一天", body="教室里静悄悄的，风吹着树叶沙沙响。",
                   px=28, author="陈安歌", out="_preview_誊抄.png"):
    cv = Canvas(PANEL_W, PANEL_H)
    font = Font("zhhei_%dpx" % px)
    topH, footH = 22, 44
    availW = PANEL_W - 24
    availH = PANEL_H - topH - footH
    cols = max(1, availW // px)
    rows = max(1, availH // px)
    cell = px
    gx = (PANEL_W - cols * cell) // 2
    gy = topH                    # 顶格排版，标题紧贴上沿
    print("scribe cols=%d rows=%d gx=%d gy=%d" % (cols, rows, gx, gy))

    header = title + (" " + author if author else "")
    headerLines = 0
    if title:
        headerLines = (len(header) + cols - 1) // cols
    rowStart = build_rows(body, cols)
    bodyRows = len(rowStart) - 1
    firstPageRows = (rows - headerLines) if (headerLines and headerLines < rows) else rows
    pages = 1 if bodyRows <= firstPageRows else \
        1 + (bodyRows - firstPageRows + rows - 1) // rows
    print("scribe bodyRows=%d pages=%d" % (bodyRows, pages))

    page = 0
    if page == 0:
        r0, r1 = 0, min(bodyRows, firstPageRows)
    else:
        r0 = firstPageRows + (page - 1) * rows
        r1 = min(bodyRows, r0 + rows)

    if title and page == 0:
        hw = text_w(header, px)
        draw_text_at(cv, font, (PANEL_W - hw) // 2, gy + px - 8, header, px)

    chars = list(body)
    for r in range(r0, r1):
        gridRow = r + headerLines if page == 0 else r
        by = gy + gridRow * cell
        for ci in range(rowStart[r], rowStart[r + 1]):
            ch = chars[ci]
            if ch in (" ", "\n", "\r"):
                continue
            cx = gx + (ci - rowStart[r]) * cell
            draw_text_at(cv, font, cx + (cell - px) // 2, by + cell - 6, ch, px)

    draw_text_at(cv, font, 14, PANEL_H - 14, "" if (title and page == 0) else title, px)
    w = text_w("%d/%d 点‹›翻页" % (page + 1, pages), px)
    draw_text_at(cv, font, PANEL_W - 14 - w, PANEL_H - 14,
                 "%d/%d 点‹›翻页" % (page + 1, pages), px)
    return cv


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--timetable-json":
        # 直接吃设备 API 的 JSON（GET /api/timetable），保证与实机数据完全一致
        import json
        raw = Path(args[1]).read_text(encoding="utf-8")
        doc = json.loads(raw)
        data = doc.get("data", doc)
        title = data.get("title", "课程表")
        dcs = []
        for d in data.get("days", []):
            segs = []
            for lab in ("am", "pm"):
                body = (d.get(lab) or "").strip()
                if not body:
                    continue
                segs.append(("上午" if lab == "am" else "下午", body))
            dcs.append((d.get("name", ""), segs))
        cv = render_timetable(dcs, title=title)
        cv.save(str(ROOT / "tools" / "_preview_课程表.png"))
        return 0
    if args[0] == "--timetable":
        dcs = DEFAULT_TT
        if len(args) > 1:
            # 形如 "周一:上午=语文、数学|下午=阅读、阅读"（| 分天，= 分上下午）
            dcs = []
            for ln in args[1].split("|"):
                parts = ln.split(":")
                name = parts[0]
                segs = []
                for p in parts[1:]:
                    if not p:
                        continue
                    if "=" in p:
                        lab, body = p.split("=", 1)
                    else:
                        lab, body = p, ""
                    segs.append((lab, body))
                dcs.append((name, segs))
        cv = render_timetable(dcs)
        cv.save(str(ROOT / "tools" / "_preview_课程表.png"))
        return 0
    if args[0] == "--scribe":
        title = "我和哪吒过一天"
        body = "教室里静悄悄的，风吹着树叶沙沙响。"
        author = ""
        px = 28
        if len(args) > 1 and args[1].endswith(".txt"):
            raw = Path(args[1]).read_text(encoding="utf-8")
            lines = raw.split("\n")
            title = lines[0].strip()
            body = "\n".join(lines[1:]).strip("\n")
            print("从文件载入: title=%r 正文 %d 字" % (title, len(body)))
        elif len(args) > 1:
            body = args[1].replace("\\n", "\n")
        cv = render_scribe(title, body, px, author)
        cv.save(str(ROOT / "tools" / "_preview_誊抄.png"))
        return 0

    text = args[0]
    px = int(args[1]) if len(args) > 1 else 28
    font = Font("zhhei_%dpx" % px)
    cv = Canvas(PANEL_W, 120)
    x, trace = draw_text_at(cv, font, 10, 70, text, px)
    print("文本 %r  总步进=%d" % (text, x - 10))
    for ch, meta, nx in trace:
        if meta is None:
            print("   %r -> 字形缺失，兜底步进" % ch)
        else:
            print("   %r  %dx%d ink  dx=%d dy=%d" %
                  (ch, meta["width"], meta["height"], meta["dx_off"], meta["dy_off"]))
    cv.save(str(ROOT / "tools" / "_preview_text.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
