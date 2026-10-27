#ifndef EPD_PROBE_H
#define EPD_PROBE_H
#include <Arduino.h>

/* 针脚定义（与 epd_panel.ino 保持一致） */
#ifndef EPD_SCK
#define EPD_SCK   11
#define EPD_MOSI  10
#define EPD_CS     9
#define EPD_DC     8
#define EPD_RST    7
#define EPD_BUSY   6
#endif

void epdProbe();

#endif
