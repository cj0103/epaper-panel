/*
 * epd_panel —— 7.5寸墨水屏 内网投屏面板（课程表 / 作文誊抄 / 公告）
 *
 * 硬件：MMK-E075A41 / 盒马红白黑三色 7.5 寸屏（主控 UC8179）
 *       + 分立墨水屏转接板 + ESP32-S3 主板
 * 接线（老方案）：SCK=11 MOSI=10 CS=9 DC=8 RST=7 BUSY=6
 * 方向：竖屏（rotation=1，逻辑 480x800）
 *
 * ★ 屏驱动选择：GDEY075Z08（gdey3c/，UC8179），不是 GDEW075Z08（epd3c/，GD7965）。
 *   两者命令集大体相同（0x01/0x04/0x06/0x10/0x13/0x50/0x61/0x90/0x91/0x92），
 *   但初始化参数、波形表、OTP 处理不同，用错会出现"能通信但不刷新/花屏"。
 *   （此条与用哪块板无关，只取决于屏的主控型号。）
 *
 * 设计（2026-10-24 与用户确认）：
 *   - 零公网依赖：删除 wttr/一言/60s新闻/NTP（内网时钟不可得，屏上不显示时间）
 *   - 内容通道：局域网 HTTP（/api/* + 手机主页），Flash(LittleFS) 断电保留
 *   - 刷新（2026-10-29 定案）：内容变化才刷；上电首刷整刷建基准，
 *     之后一律 UC8179 黑白差分快刷（画面全黑字是前提；含切模板——
 *     差分按像素驱动，整屏换代同样快，残影由定期整刷压），
 *     连续快刷每 FAST_EVERY 次强制整刷清残影；
 *     手动 /api/mode=refresh 立即整刷
 *   - 字号三档 26/28/34 雅黑；誊抄默认 26px 可选，课程表固定 28px
 *   - 配网：EEPROM 存凭据；无配置开热点 EPD-Panel-Setup；/reset 逃生入口
 *
 * 模板注册表（扩展新屏显=加模板+注册）见 render_panel.cpp 首行注释
 */
#include <U8g2_for_Adafruit_GFX.h>
#include <type_traits>
#include <EEPROM.h>

/* ---------- 取回 GxEPD2_3C 的黑缓冲 ----------
 * BW 差分快刷要"旧帧 RAM 全屏回写"（见 renderCurrent v2 注释），需要
 * 拿到 display 内部的 _black_buffer，而 GxEPD2_3C 没提供访问器。
 * 做法：给库 GxEPD2_3C.h 打了一个极小补丁（:677-682，已备份 .orig）：
 * _black_buffer 声明前插入
 *     #ifdef epd_panel_patched_public_buffer
 *         epd_panel_patched_public_buffer      ← 本文件把它定义成 public:
 *     #endif
 * 库原生构建不定义该宏 → 零影响；只有本 .ino 定义宏后，黑缓冲在本
 * 编译单元转公开。render_panel.cpp / api_panel.cpp 不含本宏，原样。
 * ⚠ 宏必须在【首次】包含 GxEPD2_3C.h 之前定义（include guard 只会
 *   展开一次），所以定义紧跟 U8g2 头之后——它是本项目唯一先于
 *   GxEPD2_3C.h 的包含。库升级时若丢了补丁，下面 static_assert 会
 *   编译失败提醒重打补丁。 */
#define epd_panel_patched_public_buffer public:
#include <GxEPD2_3C.h>
#undef epd_panel_patched_public_buffer
/* 补丁在位自检：能取 _black_buffer 的成员指针 = 补丁生效。
 * （缺补丁时这行本身会报"xxx is private"，同样能拦住并指明原因） */
typedef GxEPD2_3C<GxEPD2_750c_GDEY075Z08, GxEPD2_750c_GDEY075Z08::HEIGHT> PanelDisplay;
typedef uint8_t BlackBuf[GxEPD2_750c_GDEY075Z08::WIDTH / 8 * GxEPD2_750c_GDEY075Z08::HEIGHT];
static BlackBuf PanelDisplay::* const g_black_buffer_ptr = &PanelDisplay::_black_buffer;
/* 供 renderCurrent 取当前帧黑缓冲 */
static inline uint8_t* display_black_buffer(PanelDisplay& d) { return d.*g_black_buffer_ptr; }

#include "fonts_ink.h"
#include "panel_types.h"
#include "content_store.h"
#include "Portal.h"
#include "render_panel.h"
#include "api_panel.h"

/* ---------- 屏与字体 ---------- */
/* 接线：老方案 = 分立墨水屏转接板 + ESP32-S3 主板。
 * 转接板自带升压电路与 24pin FPC 座，7.5 寸裸屏直插转接板；
 * S3 主板只出 6 根信号线（3V3/GND 由转接板供给），GPIO 分配：
 *   SCK=11  MOSI=10  CS=9  DC=8  RST=7  BUSY=6
 * （iDevice 整合板那套是 SCK=12 MOSI=11 CS=10 DC=13 RST=14 BUSY=15，已弃用） */
#define EPD_SCK   11
#define EPD_MOSI  10
#define EPD_CS     9
#define EPD_DC     8
#define EPD_RST    7
#define EPD_BUSY   6

GxEPD2_3C<GxEPD2_750c_GDEY075Z08, GxEPD2_750c_GDEY075Z08::HEIGHT>
    display(GxEPD2_750c_GDEY075Z08(/*CS=*/ EPD_CS, /*DC=*/ EPD_DC, /*RST=*/ EPD_RST, /*BUSY=*/ EPD_BUSY));
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
  // ★ 落屏分叉（2026-10-29 v2：手搓差分协议，修复整屏换代重叠）
  //
  //  v1 用 displayWindowBW(0,8,..) 出过重叠 bug：它只把"窗口内"回写
  //  旧帧 RAM，且刷完要再传一遍整窗做回写——誊抄页→课程表页整屏换代
  //  时旧帧 RAM 与屏面失步，差分把没更新的像素当"旧→新"再翻一次，
  //  上一页文字叠在新页上（2026-10-29 照片实锤：下半屏干净、上半屏重叠）。
  //
  //  v2 直接走屏对象三层原语，全程 0x91 只出现在"写当前帧"一处，
  //  旧帧 RAM 用 writeImageToPrevious **全屏无窗口**整帧写入（0x13 通道
  //  =上一帧 black buffer），保证旧帧 RAM 与屏面永远严格同步：
  //    ① writeImageToPrevious(g_prev_black) —— 旧帧 RAM ← 上一帧（全屏）
  //    ② writeImageToCurrent(cur_black)     —— 当前帧 RAM ← 新帧（全屏）
  //    ③ refresh_bw(0,0,800,480)            —— 差分刷新（实测 ~1.4s）
  //    ④ memcpy(g_prev_black ← 当前黑缓冲)  —— 软件镜像滚动为下一帧的旧帧
  //  注意不做 _PowerOff：差分波形依赖 charge balance 维持像素状态，
  //  断电会破坏残余电荷平衡（残影加重）。
  //
  //  g_hard_refresh=true 时仍走 display(true) 整刷：writeImage 双色板
  //  全帧写 RAM + _Update_Full（~21s），清残影并把两份 RAM 都立为当前帧。
  //  ⚠ 不能 display(false)——那是只写当前软件页的三色局刷（旧 bug 根源）。
  //  前提：画面全黑字（红色不参与差分），render_panel.cpp 已无红色。
  Serial.printf("[%6lu] 绘制完成, %s 开始\n", millis(),
                g_hard_refresh ? "整刷" : "BW差分快刷");
  {
    static uint8_t* g_prev_black = nullptr;   // 上一帧黑缓冲镜像（48KB）
    const uint32_t BUF = (uint32_t)GxEPD2_750c_GDEY075Z08::WIDTH / 8 *
                         GxEPD2_750c_GDEY075Z08::HEIGHT;
    uint8_t* cur = display_black_buffer(display);
    if (g_hard_refresh || !g_prev_black) {
      if (!g_prev_black) g_prev_black = (uint8_t*)malloc(BUF);
      display.display(true);                  // 整刷内部已把两份 RAM 立为当前帧
      if (g_prev_black) memcpy(g_prev_black, cur, BUF);
    } else {
      // ★ v3.1（修复 v3 叠字回归）：前置加重刷白 + 差分，顺序不可乱。
      //   v3 翻车复盘：清屏后调了 writeScreenBuffer(0xFF,0xFF)——它把
      //   两份 RAM 一起刷白，刚写进"新帧 RAM"的内容被抹掉，差分变成
      //   白→白（啥也不驱动），随后内容只写进了"旧帧 RAM"（语义反了）
      //   → 用户所见：没刷白、直接叠字（2026-10-29 实机）。
      //   正确顺序（clear_full_bw 内部已把两份 RAM 写全白并完成刷白）：
      //    a) 旧帧 RAM ← 全白：clear_full_bw 已经写了，**不再做任何
      //       全屏覆写**（v3 的教训：任何"顺手清一下"都会毁掉基准）；
      //    b) 新帧 RAM ← 当前内容（writeImageToCurrent，只动 0x10）；
      //    c) refresh_bw 差分：白→内容；
      //    d) 镜像滚动仅供断电重启后重建，不参与差分链。
      display.epd2.clear_full_bw();
      display.epd2.writeImageToCurrent(cur, 0, 0,
          GxEPD2_750c_GDEY075Z08::WIDTH, GxEPD2_750c_GDEY075Z08::HEIGHT);
      display.epd2.refresh_bw(0, 0,
          GxEPD2_750c_GDEY075Z08::WIDTH, GxEPD2_750c_GDEY075Z08::HEIGHT);
      memcpy(g_prev_black, cur, BUF);         // 内容帧镜像滚动
    }
  }
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
void setupFull();

/* 诊断模式开关：
 *   0 = 完整固件（正常跑）
 *   1 = 诊断固件：跳过屏/SPI/存储，只跑心跳日志
 *   2 = 探针固件：只做屏链路自检 + 心跳，不进业务
 */
#define DIAG_MODE 0

void epdProbe();

void setup() {
  Serial.begin(115200);
  // 诊断打点：新版板 USB-Serial/JTAG 枚举慢，bootloader 之后给串口一点缓冲时间
  delay(300);
  Serial.println();
  Serial.printf("[%6lu] [00] setup 开始\n", millis());
#if DIAG_MODE == 1
  Serial.printf("[%6lu] [01] 跳过 SPI/display, fontProbe 前\n", millis());
  fontProbe();
  Serial.printf("[%6lu] [02] fontProbe 后, storeBegin 前\n", millis());
  if (!storeBegin()) Serial.println("[警告] storeBegin 返回失败（诊断模式预期）");
  Serial.printf("[%6lu] [03] storeBegin 返回, 进 loop 前\n", millis());
  return;
#elif DIAG_MODE == 2
  // 探针模式：先自检屏链路，再进心跳
  SPI.begin(EPD_SCK, -1, EPD_MOSI, EPD_CS);
  Serial.printf("[%6lu] [P0] SPI 已启动, 开始屏链路自检\n", millis());
  epdProbe();
  Serial.printf("[%6lu] [P1] 探针完成, 进 loop\n", millis());
  return;
#else
  setupFull();
#endif
}

void setupFull() {
  SPI.begin(EPD_SCK, -1, EPD_MOSI, EPD_CS);
  display.init(115200);
  // BUSY 极性对策：覆盖 GxEPD2 在 init() 里设的 INPUT_PULLUP。
  // 屏侧 BUSY 是推挽输出（LOW=忙 / HIGH=空闲），保持纯输入最稳；
  // 必须在 display.init() 之后设置，否则会被它改回 INPUT_PULLUP。
  pinMode(EPD_BUSY, INPUT);
  // 竖屏：面板物理 800x480、竖着摆放 → 需要 rotation=1 才能让文字正立且填满整屏。
  // GxEPD2 的方向由 Adafruit_GFX 的 setRotation 决定（drawPixel 里按 getRotation()
  // 做 90° 像素映射）。不设则停在 rotation=0（逻辑 800x480），内容会被塞进
  // 缓冲左上角、只占 60% 面积，且整幅画面相对物理方向转了 90°。
  // 若实机出现上下颠倒，把 1 改成 3。
  display.setRotation(1);
  Serial.printf("[%6lu] [03] rotation ok, fontProbe 前\n", millis());
  fontProbe();                // u8g2 桥接层字库自检（只量宽度，不落墨）
  Serial.printf("[%6lu] [04] fontProbe 后, EEPROM 前\n", millis());
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
    g_hard_refresh = true;   // 上电首刷整刷：清掉屏上残留的旧内容，建立干净基准
    renderCurrent(); // 首屏
    Serial.print("投喂主页: http://");
    Serial.println(WiFi.localIP());
  }
}

/* ---------- loop：只做服务与按需刷屏 ---------- */
void loop() {
#if DIAG_MODE
  // 诊断心跳：每 2 秒打一行，用来确认"固件活着且串口通"
  static uint32_t lastBeat = 0;
  if (millis() - lastBeat >= 2000) {
    lastBeat = millis();
    Serial.printf("[%6lu] [心跳] 固件运行中, free=%u\n", millis(), ESP.getFreeHeap());
  }
  delay(20);
  return;
#else
  if (settingMode) {
    dnsServer.processNextRequest();
  }
  webServer.handleClient();

  if (!settingMode && g_render_dirty) {
    // 快刷/整刷的抉择已在 requestRender() 里按残影计数器定好
    //（FAST_EVERY 次快刷插一次整刷，详见 api_panel.cpp）
    renderCurrent();
  }
  delay(50);
#endif
}
