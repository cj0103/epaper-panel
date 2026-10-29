/* 渲染层：竖屏 480x800（display.setRotation(1)）
 * 模板：课程表 timetable / 誊抄 scribe / 公告 notice / 提示 status
 * 首行模板登记（扩展=加新模板函数+注册表加一行）:
 *   "timetable" -> drawTimetable()
 *   "scribe"    -> drawScribe()
 *   "notice"    -> drawNotice()
 *   "status"    -> drawStatus()  (配网/错误提示)
 */
#include "render_panel.h"
#include "fonts_ink.h"

/* ---------- UTF-8 基础 ---------- */

static uint8_t u8len(unsigned char c) { return utf8Len(c); }

/* 取第 i 个字符的字节区间 */
static void utf8Nth(const String& s, unsigned int n, unsigned int& start, unsigned int& len) {
  unsigned int pos = 0, idx = 0;
  while (pos < s.length()) {
    uint8_t l = u8len(s[pos]);
    if (idx == n) { start = pos; len = l; return; }
    pos += l; idx++;
  }
  start = s.length(); len = 0;
}

/* UTF-8 字符数：复用 content_store 的 utf8Chars() */

/* 按字符数截断（超出加省略号） */
static String utf8Clip(const String& s, unsigned int maxChars) {
  if (utf8Chars(s) <= maxChars) return s;
  unsigned int st, ln;
  utf8Nth(s, maxChars - 1, st, ln);
  return s.substring(0, st + ln) + "…";
}

/* ---------- 文本宽度（u8g2） ----------
 * 空格 U+0020 不入 v1 字库（无零字节约束）：u8g2 遇未找到字形时游标行为
 * 不可靠，因此所有文本必须先按字符切分，空格由本层按字号步进补位。
 *
 * 【坑】getUTF8Width() 返回的是**墨迹像素宽**（末字换成 glyph_width 再加
 * glyph_x_offset），不是 advance（步进宽）。本字库 advance 恒等于字号，
 * 但墨迹宽随字形而变：44px 档「课」墨迹 40px、「A」墨迹 20px、「!」墨迹 5px。
 * 若用 getUTF8Width 步进，44px 档混排会字距不均、文字重叠。
 * 故步进一律走 u8g2 内部 advance（print 后读 getCursorX），宽度一律按字号累加。 */

/* 逐字绘制（空格按 px 宽跳过；步进用 u8g2 内部 advance）；返回绘制后 x。
 * 逐字路径最稳（每字符独立 setCursor+print，单字符无空格、走桥接库正常路径）。 */
static int drawTextAt(int x, int y, const String& s, int px) {
  unsigned int pos = 0;
  while (pos < s.length()) {
    uint8_t l = u8len(s[pos]);
    if (s[pos] == ' ') { x += px; pos += 1; continue; }
    String ch = s.substring(pos, pos + l);
    u8g2Fonts.setCursor(x, y);
    u8g2Fonts.print(ch);
    int nx = u8g2Fonts.getCursorX();
    x = (nx > x) ? nx : (x + px);  // 兜底：字形缺失时按字号步进
    pos += l;
  }
  return x;
}

/* 字符串宽度（advance 恒等于字号，逐字累加；空格同为字号） */
static int textW(const String& s, int px) {
  int w = 0;
  unsigned int pos = 0;
  while (pos < s.length()) {
    uint8_t l = u8len(s[pos]);
    w += px;
    pos += l;
  }
  return w;
}

/* ---------- 通用页面外框 ---------- */

/* 设置字体并切到透明背景模式。
 * 【必须】u8g2_SetFont() 在换字体时会把 is_transparent 重置为 0（画白底矩形），
 * 相邻行的白色矩形会互相擦除下缘墨迹。改透明模式后背景不落墨，
 * 屏面干净由 renderCurrent 的 fillScreen 保证。
 *
 * 【注】旧字库（基线符号写反的那版）里「一」的墨迹落在基线下方 12px，
 * 正好被下一行的白底矩形整条抹掉——曾导致课程表「周一」只剩「周」。
 * 字库已从源头修正（make_bdf.py 的 yoff 符号），但透明模式仍需保留：
 * 逗号/句号等标点墨迹仍会下沉 1~2px，透明模式可彻底避免任何擦除。 */
static void setInkFont(const uint8_t* f) {
  u8g2Fonts.setFont(f);
  u8g2Fonts.setFontMode(1);   // 1 = 透明背景
}

static void drawFooter(const String& left, const String& right) {
  setInkFont(msyh_28px);
  u8g2Fonts.setForegroundColor(GxEPD_BLACK);
  u8g2Fonts.setBackgroundColor(GxEPD_WHITE);
  drawTextAt(14, PANEL_H - 14, left, 28);
  unsigned int w = textW(right, 28);
  drawTextAt(PANEL_W - 14 - w, PANEL_H - 14, right, 28);
}

/* ---------- 课程表模板（竖屏文字列表） ----------
 * 布局（480x800 竖屏，28px 字，行距 32，每行 16 字）：
 *   标题（34px 居中，过长自动降 28px）+ 分隔线
 *   每天一块，**天标题独占一行**（红色「周一」），下面每段顶格起首：
 *     周一
 *     上午：语文、语文、数学、英语
 *     下午：阅读、体育与健康、
 *     音乐、信息技术
 *   —— 天标题独占一行后，正文可占满 16 列（不再像"天标题同排"那样缩进 2 列），
 *      按「、」断行后 5 天共 20 行，每页 21 行 → 单页可容，还余 1 行。
 *   段内容按「、」边界断行（不把词拆断），续行顶格。
 *   天块不跨页，一页放不下则分页，页脚显示页码。
 * 上传表格式 JSON 时，content_store 会自动折叠成这种"段"结构。
 */

/* 段前缀：标签 + 全角冒号（无标签则空，用于兼容旧格式的单行一天） */
static String segPrefix(const String& label) {
  if (!label.length()) return String();
  return label + "：";
}

/* 判断以 end 结尾的那个字符是不是分隔符（全角「、」E3 80 81 或半角逗号） */
static bool isSepChar(const String& s, unsigned int end) {
  if (end >= 1 && s[end - 1] == ',') return true;
  if (end >= 3 && (unsigned char)s[end - 3] == 0xE3 &&
      (unsigned char)s[end - 2] == 0x80 && (unsigned char)s[end - 1] == 0x81) return true;
  return false;
}

/* 按「、」边界断行。
 * lines != NULL：把结果写入 lines（最多 maxLines 行），返回实际写入行数；
 * lines == NULL：只统计行数（分页计算用），返回总行数。
 * 单个原子（两个「、」之间的内容）超长时按字硬切，保证不溢出。 */
static uint8_t wrapSeg(const String& s, uint8_t maxCols, String* lines, uint8_t maxLines) {
  uint8_t n = 0;
  String cur;
  unsigned int curChars = 0;
  unsigned int pos = 0;
  while (pos < s.length()) {
    // 取一个原子：到下一个分隔符（含）为止
    unsigned int start = pos, i = pos;
    while (i < s.length()) {
      i += u8len(s[i]);
      if (isSepChar(s, i)) break;
    }
    String atom = s.substring(start, i);
    unsigned int aChars = utf8Chars(atom);
    if (curChars > 0 && curChars + aChars > maxCols) {
      if (lines) { if (n < maxLines) lines[n++] = cur; } else n++;
      cur = ""; curChars = 0;
    }
    if (curChars == 0 && aChars > maxCols) {
      unsigned int ci = 0;
      while (ci < atom.length()) {
        unsigned int st, ln;
        utf8Nth(atom, ci, st, ln);
        if (curChars >= maxCols) {
          if (lines) { if (n < maxLines) lines[n++] = cur; } else n++;
          cur = ""; curChars = 0;
        }
        cur += atom.substring(st, st + ln);
        curChars++;
        ci++;
      }
    } else {
      cur += atom; curChars += aChars;
    }
    pos = i;
  }
  if (curChars > 0) {
    if (lines) { if (n < maxLines) lines[n++] = cur; } else n++;
  }
  return n;
}

void drawTimetable(const PanelTimetable& tt, PanelState& st) {
  if (!tt.valid || tt.days < 1) {  // 空表防御
    setInkFont(msyh_34px);
    u8g2Fonts.setForegroundColor(GxEPD_BLACK);
    u8g2Fonts.setBackgroundColor(GxEPD_WHITE);
    const char* tip = "暂无内容";
    u8g2Fonts.setCursor((PANEL_W - textW(String(tip), 34)) / 2, PANEL_H / 2);
    u8g2Fonts.print(tip);  // 无空格短串：直绘路径
    return;
  }
  const int margin = 16;
  const int px = 28;
  const int lineH = 30;
  const int titleBaseline = 42;
  const int sepY = 54;
  const int firstLine = 82;
  const int footY = PANEL_H - 14;
  const int lastLineFoot = footY - 40;               // 有页脚时的末行基线上限
  const int lastLineFull = PANEL_H - 12;             // 单页（不画页脚）时的上限
  const uint8_t maxCols = (PANEL_W - 2 * margin) / px;  // 16 字/行

  // 段全文（标签 + "：" + 内容），并统计每段行数
  String segFull[7][2];
  uint8_t dayLines[7] = {0};
  for (uint8_t d = 0; d < tt.days; d++) {
    uint8_t total = 0;
    uint8_t sc = tt.seg_count[d] > 2 ? 2 : tt.seg_count[d];   // 结构上限 2 段
    for (uint8_t s = 0; s < sc; s++) {
      if (!tt.seg_text[d][s].length()) continue;      // 空段不占行
      segFull[d][s] = segPrefix(tt.seg_label[d][s]) + tt.seg_text[d][s];
      total += wrapSeg(segFull[d][s], maxCols, NULL, 0);
    }
    dayLines[d] = total + 1;                         // 天标题独占一行
  }

  // 单页时省掉页脚，多腾 1 行余量；放不下再按"有页脚"分页
  int totalLines = 0;
  for (uint8_t d = 0; d < tt.days; d++) totalLines += dayLines[d];
  const int maxLinesFull = (lastLineFull - firstLine) / lineH + 1;
  const int maxLinesFoot = (lastLineFoot - firstLine) / lineH + 1;
  const bool singlePage = (totalLines <= maxLinesFull);
  const int lastLine = singlePage ? lastLineFull : lastLineFoot;

  // 分页：贪心装填，一天不拆开
  int pageFirst[8] = {0};
  uint8_t pageDays[8] = {0};
  uint8_t pg = 0;
  int used = 0;
  const int maxLinesPerPage = singlePage ? maxLinesFull : maxLinesFoot;
  for (uint8_t d = 0; d < tt.days; d++) {
    if (used > 0 && used + dayLines[d] > maxLinesPerPage) { pg++; used = 0; }
    if (pageDays[pg] == 0) pageFirst[pg] = d;
    pageDays[pg]++;
    used += dayLines[d];
  }
  uint8_t pages = pg + 1;
  st.tt_pages = pages;
  if (st.tt_page >= pages) st.tt_page = pages - 1;
  uint8_t page = st.tt_page;
  uint8_t d0 = (uint8_t)pageFirst[page];
  uint8_t d1 = (uint8_t)(d0 + pageDays[page] - 1);

  // 标题（过长自动降为 28px，仍过长则截断）
  String t = tt.title.length() ? tt.title : "课程表";
  int tpx = 34;
  if (textW(t, 34) > PANEL_W - 2 * margin) tpx = 28;
  if (textW(t, 28) > PANEL_W - 2 * margin) t = utf8Clip(t, (PANEL_W - 2 * margin) / 28);
  setInkFont(tpx == 34 ? msyh_34px : msyh_28px);
  u8g2Fonts.setForegroundColor(GxEPD_BLACK);
  u8g2Fonts.setBackgroundColor(GxEPD_WHITE);
  drawTextAt((PANEL_W - textW(t, tpx)) / 2, titleBaseline, t, tpx);
  display.drawLine(margin, sepY, PANEL_W - margin, sepY, GxEPD_BLACK);

  // 正文：天标题独占一行，段内容顶格排（可用满 16 列）
  // ★ 2026-10-29 起一律黑色（含原红色天标题/标红行）：画面无红是
  //   UC8179 黑白差分快刷（displayWindowBW）的前提。day_red/cell_red
  //   数据模型保留，恢复彩色展示时只需还原此处配色并走整刷。
  setInkFont(msyh_28px);
  int y = firstLine;
  for (uint8_t d = d0; d <= d1; d++) {
    if (y > lastLine) break;
    drawTextAt(margin, y, tt.day_names[d], px);
    y += lineH;
    uint8_t sc = tt.seg_count[d] > 2 ? 2 : tt.seg_count[d];
    for (uint8_t s = 0; s < sc; s++) {
      if (!tt.seg_text[d][s].length()) continue;
      String lines[16];
      uint8_t n = wrapSeg(segFull[d][s], maxCols, lines, 16);
      for (uint8_t i = 0; i < n; i++) {
        if (y > lastLine) break;                       // 防御：不画到页脚上
        drawTextAt(margin, y, lines[i], px);
        y += lineH;
      }
    }
  }

  // 单页不画页脚（内容要占满整页）
  if (pages > 1) {
    char pr[24];
    snprintf(pr, sizeof(pr), "%u/%u", page + 1, pages);
    drawFooter("课程表", String(pr));
  }
}

/* ---------- 誊抄模板（分页） ---------- */

/* 字号档 -> px（26/28/34 三档；默认 26 = 誊抄默认档） */
static int scribePx(const String& font) {
  if (font == "big") return 34;
  if (font == "mid") return 28;
  return 26;
}

static const uint8_t* scribeFontPtr(const String& font) {
  if (font == "big") return msyh_34px;
  if (font == "mid") return msyh_28px;
  return msyh_26px;
}

/* ★ 誊抄正文一律用**本档字号字库**画（标题+作者+正文+页脚同尺寸）。
 * 桥接库（U8g2_for_Adafruit_GFX）每行绘制都从当前 setFont 取字形，
 * 字号一混用，稿纸格子和基线就会错位——这里把"全程同档"钉死。
 * ★ u8g2_SetFont 在**换字体**时才复位透明模式（setFontMode(1)），
 *   同字体重复 setFont 是 no-op、不会复位。因此必须每页显式设一次
 *   透明模式——否则课程表画完切到誊抄（同 28px 字体）时，上一模板
 *   留下的非透明模式会让每字背后拖白底矩形、盖掉邻行下缘墨迹。
 * 返回本档 px，正文与页脚绘制共用。 */
static int scribeSetBodyFont(const String& font) {
  int px = scribePx(font);
  setInkFont(scribeFontPtr(font));
  u8g2Fonts.setFontMode(1);              // 强制透明（不依赖 setFont 是否真正切换）
  u8g2Fonts.setForegroundColor(GxEPD_BLACK);
  u8g2Fonts.setBackgroundColor(GxEPD_WHITE);
  return px;
}

/* 计算稿纸网格：返回每页字符数，输出 cols/rows/pageText 上限 */
static unsigned int scribeGrid(const PanelScribe& sc, uint8_t& cols, uint8_t& rows,
                               int& gx, int& gy, int& cell) {
  int px = scribePx(sc.font);
  int footH = 44;                       // 页脚
  int topH = 22;                        // 顶部留白：标题紧贴上沿
  int availW = PANEL_W - 24;
  int availH = PANEL_H - topH - footH;
  cols = max(1, availW / px);
  rows = max(1, availH / px);
  cell = px;
  gx = (PANEL_W - cols * cell) / 2;
  gy = topH;                            // 顶格排版（不再垂直居中，避免顶部空一大块）
  return (unsigned int)cols * rows;
}

/* ============ 正文切行（重写核心） ============
 * 旧实现是"逐格填字"：遇到行首标点就悬挂并 break 掉整行 -> 留下一整行空白；
 * 段落换行符 '\n' 还会被当成普通字符占掉一个格子。这两点就是照片里
 * 那两个"莫名其妙空行"的来源。
 *
 * 新实现先把正文切成"行"（每行记一个起始字符下标），再按行画：
 *   1. '\n' 段落换行：立即结束当前行，不占格子
 *   2. '\r' 忽略
 *   3. 行首禁则：标点不能落在行首 —— 把上一行最后一个字挤到下一行
 *      （追い出し），上一行因此少一格，但绝不会留整行空白
 */
#define SCRIBE_MAX_ROWS 340          /* 正文上限 14000 字节 ≈ 4600 字 ≈ 300 行 */
static uint16_t s_scribeRow[SCRIBE_MAX_ROWS + 1];

/* 行首禁则标点（Unicode 码点） */
static const uint32_t NO_LINE_START_CP[] = {
  0x3001, 0x3002, 0xFF0C, 0xFF01, 0xFF1F, 0xFF1B, 0xFF1A,   /* 、。，！？；： */
  0x201D, 0x2019, 0x300B, 0x300D, 0xFF09, 0x3011, 0x2026,   /* ”’》」）】… */
  0x002C, 0x002E, 0xFF0E                                /* , . 。 */
};

static bool isNoLineStart(uint32_t cp) {
  for (uint8_t i = 0; i < sizeof(NO_LINE_START_CP) / sizeof(NO_LINE_START_CP[0]); i++) {
    if (NO_LINE_START_CP[i] == cp) return true;
  }
  return false;
}

/* 取 UTF-8 字符的码点 */
static uint32_t utf8Code(const String& s, unsigned int start, unsigned int len) {
  uint32_t c = (unsigned char)s[start];
  if (len == 2) return ((c & 0x1F) << 6) | ((unsigned char)s[start + 1] & 0x3F);
  if (len == 3) return ((c & 0x0F) << 12) | (((unsigned char)s[start + 1] & 0x3F) << 6)
                      | ((unsigned char)s[start + 2] & 0x3F);
  if (len == 4) return ((c & 0x07) << 18) | (((unsigned char)s[start + 1] & 0x3F) << 12)
                      | (((unsigned char)s[start + 2] & 0x3F) << 6) | ((unsigned char)s[start + 3] & 0x3F);
  return c;
}

/* 切行：返回行数。s_scribeRow[i] = 第 i 行起始字符下标；
 * s_scribeRow[行数] = 总字符数（结束标记）。 */
static uint16_t scribeBuildRows(const PanelScribe& sc, uint8_t cols) {
  unsigned int total = utf8Chars(sc.text);
  uint16_t row = 0;                 // ★ 必须 16 位：28px 档正文超 4080 汉字时
                                    //   uint8_t 会在 255 处回绕（原 P0 bug）
  unsigned int ci = 0;
  uint8_t col = 0;
  s_scribeRow[0] = 0;
  while (ci < total && row < SCRIBE_MAX_ROWS - 1) {
    unsigned int st, ln;
    utf8Nth(sc.text, ci, st, ln);
    uint32_t cp = utf8Code(sc.text, st, ln);
    if (cp == '\r') { ci++; continue; }               // 忽略回车
    if (cp == '\n') {                                // 段落换行：结束本行
      ci++; row++;
      s_scribeRow[row] = (uint16_t)ci;
      col = 0;
      continue;
    }
    if (col >= cols) {                              // 行满
      if (col > 0 && ci > 0 && isNoLineStart(cp)) {
        ci--;                                        // 禁则：把上一字挤到下一行
        row++;
        s_scribeRow[row] = (uint16_t)ci;
        col = 0;
        continue;
      }
      row++;
      s_scribeRow[row] = (uint16_t)ci;
      col = 0;
    }
    ci++; col++;
  }
  s_scribeRow[row + 1] = (uint16_t)total;
  return row + 1;
}

/* 标题（+作者）占几行 */
static uint8_t scribeHeaderLines(const PanelScribe& sc, uint8_t cols) {
  if (!sc.title.length()) return 0;
  unsigned int n = utf8Chars(sc.title) + (sc.author.length() ? utf8Chars(sc.author) + 1 : 0);
  return (uint8_t)((n + cols - 1) / cols);
}

unsigned int scribeTotalPages(const PanelScribe& sc) {
  uint8_t cols, rows;
  int gx, gy, cell;
  scribeGrid(sc, cols, rows, gx, gy, cell);
  uint16_t bodyRows = scribeBuildRows(sc, cols);
  uint8_t headerLines = scribeHeaderLines(sc, cols);
  unsigned int firstPageRows = (headerLines && headerLines < rows) ? (rows - headerLines) : rows;
  if (bodyRows <= firstPageRows) return 1;
  return 1 + (bodyRows - firstPageRows + rows - 1) / rows;
}

static void drawScribeImpl(const PanelScribe& sc, PanelState& st) {
  uint8_t cols, rows;
  int gx, gy, cell;
  scribeGrid(sc, cols, rows, gx, gy, cell);
  uint16_t bodyRows = scribeBuildRows(sc, cols);
  bool hasHeader = sc.title.length() > 0;
  uint8_t headerLines = scribeHeaderLines(sc, cols);
  const int backPx = scribeSetBodyFont(sc.font);   // 全程同档（见函数注释）

  // 分页规则：首页 = 标题行(headerLines) + 剩余行正文；后续页 = 整页正文
  unsigned int linesPerPage = rows;
  unsigned int firstPageRows = (hasHeader && headerLines < linesPerPage)
                                 ? linesPerPage - headerLines
                                 : linesPerPage;

  unsigned int pages;
  if (bodyRows <= firstPageRows) {
    pages = 1;
  } else {
    pages = 1 + (bodyRows - firstPageRows + linesPerPage - 1) / linesPerPage;
  }
  st.scribe_pages = pages;
  if (st.scribe_page >= pages) st.scribe_page = pages - 1;
  unsigned int page = st.scribe_page;

  // 本页正文行范围（行下标，相对正文）
  unsigned int r0, r1;
  if (page == 0) {
    r0 = 0;
    r1 = (bodyRows < firstPageRows) ? bodyRows : firstPageRows;
  } else {
    r0 = firstPageRows + (page - 1) * linesPerPage;
    r1 = r0 + linesPerPage;
    if (r1 > bodyRows) r1 = bodyRows;
  }

  // ---- 标题（第一页，网格顶部行居中；用本档字库，已在函数入口设好）----
  if (hasHeader && page == 0) {
    String header = sc.title;
    if (sc.author.length()) { header += " "; header += sc.author; }
    String h = utf8Clip(header, (unsigned int)headerLines * cols);
    int hw = textW(h, backPx);
    drawTextAt((PANEL_W - hw) / 2, gy + backPx - 8, h, backPx);
  }

  // ---- 正文逐行绘制（每行按行内序号定位到格子）----
  const int pxs = backPx;
  for (unsigned int r = r0; r < r1; r++) {
    // ★ 本页格行号 = 全局行号 - 本页起始行号；标题行只占首页顶部。
    //   （曾用 gridRow=r 直接拿全局行号，第2页 by=22+27*26=724，
    //   内容全被推到屏幕底部、上部大片空白——2026-10-28 实机确认）
    int gridRow = (int)(r - r0) + ((page == 0) ? (int)headerLines : 0);
    int by = gy + gridRow * cell;
    unsigned int from = s_scribeRow[r], to = s_scribeRow[r + 1];
    for (unsigned int ci = from; ci < to; ci++) {
      unsigned int cst, cln;
      utf8Nth(sc.text, ci, cst, cln);
      String ch(sc.text.c_str() + cst, cln);
      if (ch == " " || ch == "\n" || ch == "\r") continue;
      int cx = gx + (int)(ci - from) * cell;
      u8g2Fonts.setCursor(cx + (cell - pxs) / 2, by + cell - 6);
      u8g2Fonts.print(ch);
    }
  }

  // 页码（仍用本档字号，避免混档）
  char pr[24];
  snprintf(pr, sizeof(pr), "%u/%u", page + 1, pages);
  String right = String(pr) + " 点‹›翻页";
  unsigned int rw = textW(right, backPx);
  drawTextAt(PANEL_W - 14 - rw, PANEL_H - 14, right, backPx);
  if (!(hasHeader && page == 0) && sc.title.length()) {
    drawTextAt(14, PANEL_H - 14, utf8Clip(sc.title, (PANEL_W - 40 - rw) / backPx), backPx);
  }
}

void drawScribe(const PanelScribe& sc, PanelState& st) { drawScribeImpl(sc, st); }

/* ---------- 公告模板 ---------- */

void drawNotice(const String& text) {
  // 44px 档已随字库下线，公告用最大档 34px：13 字/行
  // ★ 原红字改黑：全画面无红是黑白差分快刷的前提（2026-10-29）
  setInkFont(msyh_34px);
  u8g2Fonts.setForegroundColor(GxEPD_BLACK);
  u8g2Fonts.setBackgroundColor(GxEPD_WHITE);
  unsigned int n = utf8Chars(text);
  unsigned int lines = (n + 12) / 13;
  unsigned int y = PANEL_H / 2 - (lines * 48) / 2 + 34;
  for (unsigned int l = 0; l < lines; l++) {
    String line;
    for (unsigned int i = l * 13; i < min(n, (l + 1) * 13); i++) {
      unsigned int st, ln;
      utf8Nth(text, i, st, ln);
      line += text.substring(st, st + ln);
    }
    int w = textW(line, 34);
    drawTextAt((PANEL_W - w) / 2, y, line, 34);
    y += 48;
  }
  drawFooter("临时公告", "");
}

/* ---------- 状态模板（配网/提示，多行） ---------- */

void drawStatus(const String& text) {
  display.fillScreen(GxEPD_WHITE);
  setInkFont(msyh_34px);
  u8g2Fonts.setForegroundColor(GxEPD_BLACK);
  u8g2Fonts.setBackgroundColor(GxEPD_WHITE);
  int lineH = 56;
  int y = PANEL_H / 2 - (text.length() ? std::count(text.begin(), text.end(), '\n') : 0) * lineH / 2;
  int pos = 0;
  while (pos <= (int)text.length()) {
    int nl = text.indexOf('\n', pos);
    String line = (nl < 0) ? text.substring(pos) : text.substring(pos, nl);
    int w = textW(line, 34);
    drawTextAt((PANEL_W - w) / 2, y, line, 34);
    y += lineH;
    if (nl < 0) break;
    pos = nl + 1;
  }
  display.display();
}
