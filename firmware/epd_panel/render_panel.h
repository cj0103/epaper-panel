#ifndef RENDER_PANEL_H
#define RENDER_PANEL_H
#include <Arduino.h>
#include <GxEPD2_3C.h>
#include <U8g2_for_Adafruit_GFX.h>
#include "panel_types.h"
#include "content_store.h"

/* 竖屏逻辑分辨率（rotation=1：物理 800x480 横屏竖用） */
#define PANEL_W 480
#define PANEL_H 800

/* 屏驱动：UC8179（盒马红白黑三色 7.5 寸），见 epd_panel.ino 顶部说明。
 * 注意与 .ino 里的实例化保持一致，改一处必须改两处。 */
extern GxEPD2_3C<GxEPD2_750c_GDEY075Z08, GxEPD2_750c_GDEY075Z08::HEIGHT> display;
extern U8G2_FOR_ADAFRUIT_GFX u8g2Fonts;

void drawTimetable(const PanelTimetable& tt, PanelState& st);   // 内部按天分页并写回总页数
void drawScribe(const PanelScribe& sc, PanelState& st);   // 内部用 st.scribe_page 分页并回写总页数
unsigned int scribeTotalPages(const PanelScribe& sc);
void drawNotice(const String& text);
void drawStatus(const String& text);   // 自带 display()（配网早期独立使用）

#endif
