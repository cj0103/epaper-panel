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

/* 连续快刷多少次后强制插一次整刷清残影（差分快刷的物理代价是残影累积，
 * 所有墨水屏局刷方案的标准做法）。
 * 10→6：2026-10-29 实机照片评估，10 次窗口内"脏底"累积肉眼可见，
 * 收紧到 6 让残影活不过一个短周期。若观感仍不满意，下一步是定制
 * 驱动 0x20~0x25 LUT 加重单次驱动（更快刷更干净但变慢，见当日日志）。 */
#define FAST_EVERY 6

/* 统一渲染请求：先清待办再置位；按残影计数器决定本次快刷还是整刷
 * （刷新策略详见 api_panel.cpp 注释）。
 * 任何外部模块（如 portal 配网页）要触发刷屏都必须走它。 */
void requestRender();

/* 强制整刷：仅手动 /api/mode=refresh（用户显式要求清残影）。
 * 切模板/翻页/推送都走 requestRender() 的快刷通道。 */
void requestFullRender();

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
