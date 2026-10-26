/*
 * epd_panel —— 7.5寸墨水屏 内网投屏面板（课程表 / 作文誊抄 / 公告）
 *
 * 硬件：MMK-E075A41(UC8179, 按 GDEW075Z08 驱动) + ESP32-S3 N16R8
 * 接线：SCK=11 MOSI=10 CS=9 DC=8 RST=7 BUSY=6 VCC=3V3
 * 方向：竖屏（rotation=1，逻辑 480x800）
 *
 * 设计（2026-10-24 与用户确认）：
 *   - 零公网依赖：删除 wttr/一言/60s新闻/NTP（内网时钟不可得，屏上不显示时间）
 *   - 内容通道：局域网 HTTP（/api/* + 手机主页），Flash(LittleFS) 断电保留
 *   - 刷新：内容变化才刷；誊抄翻页快刷，每 4 次快刷整刷清残影；手动 /api/mode=refresh
 *   - 字号三档 big44/mid34/small28（默认 small=D档≈350字/页），手机端可选
 *   - 配网：EEPROM 存凭据；无配置开热点 EPD-Panel-Setup；/reset 逃生入口
 *
 * 模板注册表（扩展新屏显=加模板+注册）见 render_panel.cpp 首行注释
 */
#include <U8g2_for_Adafruit_GFX.h>
#include <GxEPD2_3C.h>
#include <EEPROM.h>

#include "fonts_ink.h"
#include "panel_types.h"
#include "content_store.h"
#include "Portal.h"
#include "render_panel.h"
#include "api_panel.h"

/* ---------- 屏与字体 ---------- */
/* 接线：iDevice 墨水屏驱动板（ESP32-S3 版，S3-WROOM-1 N16R8 模组）。
 * 该整合板 3.3V/GND 已板内直连，外部只接 6 根信号线，
 * GPIO 分配取自厂家针脚表 ESP32-S3 行：
 *   SCK=12  MOSI=11  CS=10  DC=13  RST=14  BUSY=15
 * （旧的分立驱动板接线为 SCK=11 MOSI=10 CS=9 DC=8 RST=7 BUSY=6，已弃用） */
#define EPD_SCK   12
#define EPD_MOSI  11
#define EPD_CS    10
#define EPD_DC    13
#define EPD_RST   14
#define EPD_BUSY  15

GxEPD2_3C<GxEPD2_750c_GDEW075Z08, GxEPD2_750c_GDEW075Z08::HEIGHT>
    display(GxEPD2_750c_GDEW075Z08(/*CS=*/ EPD_CS, /*DC=*/ EPD_DC, /*RST=*/ EPD_RST, /*BUSY=*/ EPD_BUSY));
U8G2_FOR_ADAFRUIT_GFX u8g2Fonts;

/* ---------- 全局状态 ---------- */
PanelState g_panel;

/* ---------- 配网回调（portal_impl.cpp 调用） ---------- */
void portalShowStatus(const String& text) { drawStatus(text); }

/* ---------- 出厂内置示例课程表（首次启动落盘，上传即覆盖） ---------- */
static const char* DEFAULT_TIMETABLE = R"json({
  "title": "课程表（内置示例）",
  "days": ["周一","周二","周三","周四","周五"],
  "periods": ["早读","第1节","第2节","午写","第3节","第4节","课后"],
  "cells": [
    ["语文","英语","语文","数学","英语"],
    ["数学","语文","数学","语文","数学"],
    ["英语","数学","英语","英语","语文"],
    ["写字","阅读","写字","阅读","写字"],
    ["体育","音乐","美术","体育","科学"],
    ["道德","科学","体育","美术","音乐"],
    ["班会","劳动","书法","作业","作业"]
  ]
})json";

static void ensureDefaultTimetable() {
  if (g_panel.tt.valid) return;
  String err;
  if (storeSaveTimetable(DEFAULT_TIMETABLE, err)) {
    storeLoadTimetable(g_panel.tt);
    Serial.println("[启动] 已写入内置示例课程表");
  }
}

/* ---------- 渲染派发 ---------- */
static void renderCurrent() {
  Serial.printf("[%6lu] 渲染开始 mode=%s\n", millis(), g_panel.mode.c_str());
  display.fillScreen(GxEPD_WHITE);
  Serial.printf("[%6lu] fill 完成, 绘制中\n", millis());
  if (g_panel.mode == "scribe" && g_panel.sc.valid) {
    drawScribe(g_panel.sc, g_panel);
  } else if (g_panel.mode == "notice" && g_panel.notice.length()) {
    drawNotice(g_panel.notice);
  } else {
    drawTimetable(g_panel.tt, g_panel);
  }
  Serial.printf("[%6lu] 绘制完成, display(%d) 开始\n", millis(), g_hard_refresh);
  display.display(g_hard_refresh); // true=整屏刷新清残影, false=快刷
  Serial.printf("[%6lu] display 完成\n", millis());
  g_hard_refresh = false;
  g_render_dirty = false;
  // 页数按当前模式报（别写死成誊抄的页数，否则课程表模式会误报）
  if (g_panel.mode == "scribe") {
    Serial.printf("[渲染] mode=%s page=%u/%u\n", g_panel.mode.c_str(),
                  g_panel.scribe_page + 1, g_panel.scribe_pages);
  } else if (g_panel.mode == "timetable") {
    Serial.printf("[渲染] mode=%s page=%u/%u\n", g_panel.mode.c_str(),
                  g_panel.tt_page + 1, g_panel.tt_pages);
  } else {
    Serial.printf("[渲染] mode=%s\n", g_panel.mode.c_str());
  }
}

/* ---------- setup ---------- */
/* 字库自检：仅做串口测量，不往屏幕写东西。
 * （早期版本曾用 Adafruit_GFX 的 setFont+drawChar 直绘自检，那是错的——
 *   GFXfont 与 u8g2 v1 是两种完全不同的格式，v1 字库喂给 GFX 会画出乱码。
 *   现在的自检统一走 u8g2 桥接层，只量宽度不落墨。） */
void fontProbe();

void setup() {
  Serial.begin(115200);
  SPI.begin(EPD_SCK, -1, EPD_MOSI, EPD_CS);
  display.init(115200);
  // 竖屏：面板物理 800x480、竖着摆放 → 需要 rotation=1 才能让文字正立且填满整屏。
  // GxEPD2 的方向由 Adafruit_GFX 的 setRotation 决定（drawPixel 里按 getRotation()
  // 做 90° 像素映射）。不设则停在 rotation=0（逻辑 800x480），内容会被塞进
  // 缓冲左上角、只占 60% 面积，且整幅画面相对物理方向转了 90°。
  // 若实机出现上下颠倒，把 1 改成 3。
  display.setRotation(1);
  // 无 BUSY 线（价签类屏常见）时 GPIO15 悬空 → 下拉读出稳定"空闲"，
  // 避免 GxEPD2 等 BUSY 撞满超时；有 BUSY 线时上拉驱动也能压过下拉。
  pinMode(EPD_BUSY, INPUT_PULLDOWN);
  SPI.begin(EPD_SCK, -1, EPD_MOSI, EPD_CS);
  fontProbe();                // u8g2 桥接层字库自检（只量宽度，不落墨）
  EEPROM.begin(4096);
  u8g2Fonts.begin(display);   // 最后绑定，确保桥接层读到最终旋转状态

  Serial.printf("[%6lu] 进入 setup 存储初始化\n", millis());
  if (!storeBegin()) Serial.println("[警告] LittleFS 挂载失败");
  Serial.printf("[%6lu] LittleFS OK, 读模式\n", millis());
  g_panel.mode = modeRead();
  storeLoadTimetable(g_panel.tt);
  storeLoadScribe(g_panel.sc);
  Serial.printf("[%6lu] 内容加载完 tt=%d sc=%d\n", millis(), g_panel.tt.valid, g_panel.sc.valid);
  ensureDefaultTimetable();
  Serial.printf("[%6lu] wifi_init 前\n", millis());

  wifi_init();
  Serial.printf("[%6lu] wifi_init 后 settingMode=%d\n", millis(), settingMode);
  if (!settingMode) {
    registerPanelRoutes();
    Serial.println("routes ok");
    renderCurrent(); // 首屏
    Serial.print("投喂主页: http://");
    Serial.println(WiFi.localIP());
  }
}

/* ---------- loop：只做服务与按需刷屏 ---------- */
void loop() {
  if (settingMode) {
    dnsServer.processNextRequest();
  }
  webServer.handleClient();

  if (!settingMode && g_render_dirty) {
    static uint8_t fastRefreshCount = 0;
    // 快刷计满 4 次强制整刷一次，抑制残影
    if (!g_hard_refresh) {
      fastRefreshCount++;
      if (fastRefreshCount >= 4) { g_hard_refresh = true; fastRefreshCount = 0; }
    }
    renderCurrent();
  }
  delay(50);
}
