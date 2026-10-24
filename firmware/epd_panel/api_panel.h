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
