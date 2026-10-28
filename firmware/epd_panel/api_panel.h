#ifndef API_PANEL_H
#define API_PANEL_H
#include <Arduino.h>
#include <WiFi.h>
#include "Portal.h"
#include "panel_types.h"
#include "content_store.h"
#include "render_panel.h"

extern volatile bool g_render_dirty;
extern volatile bool g_hard_refresh;

/* 统一渲染请求：先清待办再置位，强制整刷（见 api_panel.cpp 注释——
 * 整屏重绘模式下 GxEPD2 的快刷只重写当前软件页，会残留旧内容）。
 * 任何外部模块（如 portal 配网页）要触发刷屏都必须走它。 */
void requestRender();

void registerPanelRoutes();
void handleHome();
void handleTimetablePage();
void handleApiTimetable();
void handleApiTimetableGet();
void handleApiScribe();
void handleApiScribeGet();
void handleApiDisplay();
void handleApiMode();
void handleApiStatus();

#endif
