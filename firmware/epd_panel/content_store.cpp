/* Flash 内容仓库：LittleFS JSON 文件读写 + UTF-8 工具
 * 文件约定（扩展内容=加新文件+协议结构体，不动旧数据）：
 *   /timetable.json  课程表
 *   /scribe.json     誊抄内容
 *   /mode.txt        当前模式
 */
#include "content_store.h"
#include <LittleFS.h>
#include <ArduinoJson.h>

/* ---------- UTF-8 工具 ---------- */

uint8_t utf8Len(unsigned char c) {
  if (c < 0x80) return 1;
  if ((c >> 5) == 0x6) return 2;
  if ((c >> 4) == 0xE) return 3;
  if ((c >> 3) == 0x1E) return 4;
  return 1; // 非法字节按 1 跳过，防死循环
}

unsigned int utf8Chars(const String& s) {
  unsigned int n = 0, pos = 0;
  while (pos < s.length()) { pos += utf8Len(s[pos]); n++; }
  return n;
}

String utf8TrimBytes(String s, unsigned int maxBytes) {
  if (s.length() <= maxBytes) return s;
  unsigned int cut = maxBytes;
  // 回退到字符边界
  while (cut > 0 && (s[cut] & 0xC0) == 0x80) cut--;
  return s.substring(0, cut) + "…";
}

static void readFileAll(const char* path, String& out) {
  out = "";
  File f = LittleFS.open(path, "r");
  if (!f) return;
  out = f.readString();
  f.close();
}

/* 去掉换行符：课程表的单段内容必须是单行 */
static String stripEol(String s) {
  s.replace("\r", "");
  s.replace("\n", "");
  return s;
}

static bool writeFileAll(const char* path, const String& content) {
  File f = LittleFS.open(path, "w");
  if (!f) return false;
  size_t w = f.print(content);
  f.close();
  return w == content.length();
}

/* ---------- 初始化 ---------- */

bool storeBegin() {
  // 兼容不同分区表的数据分区标签（app3M_fat9M 方案为 ffat，默认方案多为 spiffs）
  if (LittleFS.begin(true, "/fs", 5, "ffat")) return true;
  if (LittleFS.begin(true, "/fs", 5, "spiffs")) return true;
  return false;
}

/* ---------- 模式 ---------- */

String modeRead() {
  String s;
  readFileAll("/mode.txt", s);
  s.trim();
  if (s == "scribe" || s == "notice" || s == "timetable") return s;
  return "timetable";
}

bool modeWrite(const String& mode) {
  return writeFileAll("/mode.txt", mode);
}

/* ---------- 课程表 ---------- */

/* 读回原始 JSON（供二级页面回填表单用） */
bool storeReadTimetableRaw(String& out) {
  readFileAll("/timetable.json", out);
  out.trim();
  return out.length() > 0;
}

bool storeSaveTimetable(const String& jsonIn, String& err) {
  DynamicJsonDocument doc(16384);
  if (deserializeJson(doc, jsonIn) != DeserializationError::Ok) {
    err = "JSON 解析失败";
    return false;
  }
  // 兼容四种格式：
  //   主格式  days = [{name, am, pm}, ...]
  //   文字版  text = "周一：语文、数学\n..."
  //   行式    days = ["周一", ...] + courses = ["语文、数学", ...]
  //   表格    days + periods + cells
  bool isText = doc["text"].is<const char*>();
  bool isList = doc["courses"].is<JsonArray>();
  bool isTable = doc["periods"].is<JsonArray>() && doc["cells"].is<JsonArray>();

  if (isText) {
    if (strlen(doc["text"].as<const char*>()) > 600) {
      err = "text 过长（上限 600 字节）";
      return false;
    }
  } else {
    JsonArray days = doc["days"];
    if (!doc["days"].is<JsonArray>() || days.size() < 1 || days.size() > 7) {
      err = "days 须为 1-7 天";
      return false;
    }
    // days 是对象数组还是字符串数组？
    bool objFmt = true;
    for (JsonVariant d : days) {
      if (!d.is<JsonObject>()) { objFmt = false; break; }
    }
    if (objFmt) {
      // 主格式：逐项校验 name / am / pm
      for (JsonVariant d : days) {
        JsonObject o = d.as<JsonObject>();
        if (!o["name"].is<const char*>() || !o["name"].as<const char*>()[0]) {
          err = "每项须有 name";
          return false;
        }
        if (o["am"].is<const char*>() && strlen(o["am"].as<const char*>()) > 60) {
          err = "单段课程过长（上限 60 字节）";
          return false;
        }
        if (o["pm"].is<const char*>() && strlen(o["pm"].as<const char*>()) > 60) {
          err = "单段课程过长（上限 60 字节）";
          return false;
        }
      }
    } else if (isList) {
      JsonArray courses = doc["courses"];
      if (courses.size() != days.size()) { err = "courses 长度须等于 days"; return false; }
      for (JsonVariant c : courses) {
        if (c.as<String>().length() > 40) { err = "单日课程过长（上限 40 字节）"; return false; }
      }
    } else if (isTable) {
      JsonArray periods = doc["periods"];
      JsonArray cells = doc["cells"];
      if (periods.size() < 1 || periods.size() > 12) { err = "periods 须为 1-12 节"; return false; }
      if ((int)cells.size() != (int)periods.size()) { err = "cells 行数须等于 periods"; return false; }
      for (JsonVariant row : cells) {
        if (!row.is<JsonArray>()) { err = "cells 须为二维数组"; return false; }
        if ((int)row.as<JsonArray>().size() != (int)days.size()) { err = "cells 每行列数须等于 days"; return false; }
      }
    } else {
      err = "days 须为对象数组 {name,am,pm}";
      return false;
    }
  }
  // 结构合法，原样落盘
  if (!writeFileAll("/timetable.json", jsonIn)) {
    err = "写入 Flash 失败";
    return false;
  }
  return true;
}

bool storeLoadTimetable(PanelTimetable& tt) {
  String raw;
  readFileAll("/timetable.json", raw);
  tt.valid = false;
  if (raw.length() == 0) return false;
  DynamicJsonDocument doc(16384);
  if (deserializeJson(doc, raw) != DeserializationError::Ok) return false;
  if (!doc["days"].is<JsonArray>() && !doc["text"].is<const char*>()) return false;
  tt.title = doc["title"].is<const char*>() ? doc["title"].as<String>() : "课程表";

  for (uint8_t i = 0; i < 7; i++) {
    tt.seg_count[i] = 0;
    tt.day_red[i] = false;
    for (uint8_t s = 0; s < 2; s++) { tt.seg_label[i][s] = ""; tt.seg_text[i][s] = ""; }
  }

  if (doc["text"].is<const char*>()) {
    // 文字版：每行一天，如 "周一：语文、数学、英语"
    const char* txt = doc["text"].as<const char*>();
    String all(txt);
    uint8_t d = 0;
    int start = 0;
    while (start <= (int)all.length() && d < 7) {
      int nl = all.indexOf('\n', start);
      String line = (nl < 0) ? all.substring(start) : all.substring(start, nl);
      line.trim();
      if (line.length()) {
        int sep = line.indexOf('：');
        if (sep < 0) sep = line.indexOf(':');
        if (sep > 0) {
          tt.day_names[d] = line.substring(0, sep);
          tt.day_names[d].trim();
          tt.seg_text[d][0] = line.substring(sep + 1);
        } else {
          tt.day_names[d] = line;
        }
        tt.seg_text[d][0].trim();
        tt.seg_count[d] = 1;
        d++;
      }
      if (nl < 0) break;
      start = nl + 1;
    }
    tt.days = d;
    if (tt.days < 1) return false;
  } else {
    JsonArray days = doc["days"];
    tt.days = days.size();
    if (tt.days < 1 || tt.days > 7) return false;
    // 主格式：days 是对象数组 {name, am, pm}
    bool objFmt = true;
    for (JsonVariant d : days) {
      if (!d.is<JsonObject>()) { objFmt = false; break; }
    }
    if (objFmt) {
      uint8_t i = 0;
      for (JsonVariant d : days) {
        JsonObject o = d.as<JsonObject>();
        tt.day_names[i] = o["name"].is<const char*>() ? o["name"].as<String>() : "";
        tt.day_names[i].trim();
        uint8_t seg = 0;
        const char* am = o["am"].is<const char*>() ? o["am"].as<const char*>() : "";
        const char* pm = o["pm"].is<const char*>() ? o["pm"].as<const char*>() : "";
        String a(am); a.trim(); a = stripEol(a);
        String p(pm); p.trim(); p = stripEol(p);
        if (a.length()) { tt.seg_label[i][seg] = "上午"; tt.seg_text[i][seg] = a; seg++; }
        if (p.length()) { tt.seg_label[i][seg] = "下午"; tt.seg_text[i][seg] = p; seg++; }
        tt.seg_count[i] = seg;
        i++;
      }
    } else {
      for (uint8_t i = 0; i < tt.days; i++) tt.day_names[i] = days[i].as<String>();
    }
  }

  if (!doc["text"].is<const char*>()) {
    if (doc["courses"].is<JsonArray>()) {
      // 行式：每天一段（无标签）
      JsonArray courses = doc["courses"];
      for (uint8_t i = 0; i < tt.days; i++) {
        tt.seg_text[i][0] = stripEol(courses[i].as<String>());
        tt.seg_text[i][0].trim();
        tt.seg_count[i] = 1;
      }
    } else if (doc["periods"].is<JsonArray>() && doc["cells"].is<JsonArray>()) {
      // 表格式：折叠成一天一段 —— 该天的非空科目用"、"连接
      JsonArray periods = doc["periods"];
      JsonArray cells = doc["cells"];
      tt.periods = periods.size();
      if (tt.periods < 1 || tt.periods > 12) return false;
      if ((int)cells.size() != (int)tt.periods) return false;
      for (uint8_t r = 0; r < tt.periods; r++) {
        tt.period_names[r] = periods[r].as<String>();
        JsonArray row = cells[r];
        if ((int)row.size() != (int)tt.days) return false;
        for (uint8_t c = 0; c < tt.days; c++) tt.cells[r][c] = row[c].as<String>();
      }
      JsonArray colors = doc["cell_colors"];
      for (uint8_t r = 0; r < tt.periods; r++) {
        for (uint8_t c = 0; c < tt.days; c++) {
          tt.cell_red[r][c] = false;
          if (!colors.isNull() && colors.size() > r && colors[r].size() > c)
            tt.cell_red[r][c] = colors[r][c].as<int>() != 0;
        }
      }
      for (uint8_t c = 0; c < tt.days; c++) {
        String line;
        for (uint8_t r = 0; r < tt.periods; r++) {
          String v = tt.cells[r][c];
          v.trim();
          if (!v.length()) continue;
          if (line.length()) line += "、";
          line += v;
          if (tt.cell_red[r][c]) tt.day_red[c] = true;
        }
        tt.seg_text[c][0] = line;
        tt.seg_count[c] = 1;
      }
    }
  }
  tt.valid = true;
  return true;
}

/* ---------- 誊抄 ---------- */

/* 读回原始 JSON（供调试/回填用） */
bool storeReadScribeRaw(String& out) {
  readFileAll("/scribe.json", out);
  out.trim();
  return out.length() > 0;
}

bool storeSaveScribe(const String& jsonIn, String& err) {
  DynamicJsonDocument doc(16384);
  if (deserializeJson(doc, jsonIn) != DeserializationError::Ok) {
    err = "JSON 解析失败";
    return false;
  }
  if (!doc["text"].is<const char*>() || strlen(doc["text"]) == 0) {
    err = "缺少字段: text";
    return false;
  }
  const char* fnt = doc["font"].is<const char*>() ? doc["font"].as<const char*>() : "small";
  if (strcmp(fnt, "big") && strcmp(fnt, "mid") && strcmp(fnt, "small")) {
    err = "font 只能是 big/mid/small";
    return false;
  }
  if (doc["text"].as<String>().length() > 14000) { // 4页 x 350字 x 4字节，超限即拒
    err = "文本过长（上限约14000字节，更多分页建议拆分）";
    return false;
  }
  if (!writeFileAll("/scribe.json", jsonIn)) {
    err = "写入 Flash 失败";
    return false;
  }
  return true;
}

bool storeLoadScribe(PanelScribe& sc) {
  String raw;
  readFileAll("/scribe.json", raw);
  sc.valid = false;
  if (raw.length() == 0) return false;
  DynamicJsonDocument doc(16384);
  if (deserializeJson(doc, raw) != DeserializationError::Ok) return false;
  if (!doc["text"].is<const char*>()) return false;
  sc.text = doc["text"].as<String>();
  sc.title = doc["title"].is<const char*>() ? doc["title"].as<String>() : "";
  sc.author = doc["author"].is<const char*>() ? doc["author"].as<String>() : "";
  sc.font = doc["font"].is<const char*>() ? doc["font"].as<String>() : "small";
  sc.valid = true;
  return true;
}
