/* 内容数据结构（Flash 持久化，LittleFS JSON 文件） */
#ifndef PANEL_TYPES_H
#define PANEL_TYPES_H

#include <Arduino.h>
#include <WString.h>

/* ---- 课程表 ----
 * 屏幕版式（480x800 竖屏）：
 *   标题（居中，自动缩字号） + 分隔线
 *   每天一块：红色「周一」+ 上午/下午两段课程（"、"连接，超长自动换行）
 *
 * JSON 协议（主格式，二级页面 /tt 提交的就是它）：
 * { "title": "四 1 班课程表（游泳周）",
 *   "days": [
 *     {"name":"周一","am":"语文、语文、数学、英语",
 *                "pm":"阅读、体育与健康、音乐、信息技术"},
 *     ... ] }                                   // days 最多 7 天
 *   am/pm 可留空（留空则该段不显示），段名固定 上午/下午。
 *
 * 兼容旧格式（上传后自动折成同样的"段"结构）：
 * A. 行式：{"title":..,"days":["周一",..],"courses":["语文、数学",..]}
 * A'. 文字版：{"title":..,"text":"周一：语文、数学\n周二：数学、语文"}
 * B. 表格式：{"title":..,"days":[..],"periods":[..],"cells":[[..],..]}
 */
struct PanelTimetable {
  String title;
  uint8_t days = 0;
  String day_names[7];
  /* 每天的段（上午/下午），seg_count=1 时标签可为空（兼容旧格式的单行一天） */
  uint8_t seg_count[7] = {0};
  String seg_label[7][2];   // "上午" / "下午"
  String seg_text[7][2];    // 段内课程，"、"连接
  bool   day_red[7];        // 该天是否含红字科目（整行标红）
  // 旧表格格式保留：上传表格 JSON 时自动折叠
  uint8_t periods = 0;
  String period_names[12];
  String cells[12][7];
  bool cell_red[12][7];
  bool valid = false;
};

/* ---- 誊抄内容（作文等） ----
 * JSON 协议:
 * { "title": "《我的妈妈》", "author": "（原文）", "font": "small",
 *   "text": "正文……（\\n 换行，自动排版）" }
 * font: big=44px / mid=34px / small=28px（默认 small=D档） */
struct PanelScribe {
  String title;
  String author;
  String font;   // big | mid | small
  String text;
  bool valid = false;
};

/* ---- 全局状态（内存镜像，写 Flash 时序列化） ---- */
struct PanelState {
  String mode = "timetable";   // timetable | scribe | notice
  PanelTimetable tt;
  PanelScribe sc;
  String notice;               // /api/display 临时公告（不落盘）
  uint8_t scribe_page = 0;     // 誊抄当前页（0 基）
  uint8_t scribe_pages = 1;    // 誊抄总页数
  uint8_t tt_page = 0;         // 课程表当前页（0 基）
  uint8_t tt_pages = 1;        // 课程表总页数
};

#endif
