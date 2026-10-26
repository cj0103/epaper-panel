#ifndef EPD_PROBE_H
#define EPD_PROBE_H
#include <Arduino.h>

/* 针脚定义（与 epd_panel.ino 保持一致） */
#ifndef EPD_SCK
#define EPD_SCK   12
#define EPD_MOSI  11
#define EPD_CS    10
#define EPD_DC    13
#define EPD_RST   14
#define EPD_BUSY  15
#endif

void epdProbe();

#endif
