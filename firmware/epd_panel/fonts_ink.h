// 自动生成：u8g2 v1 中文字库声明（微软雅黑 26/28/34）
#ifndef FONTS_INK_H
#define FONTS_INK_H
#include <stdint.h>

// 每档字号一个字体，含 ASCII + GB2312 + CJK 统一表意 + 中文标点。
// 字形宽度由 bdfconv 统一（build mode 见 gen_fonts_v1.py），
// advance 宽度 = 字号（等宽），空格不入字库（渲染层按字号步进）。
extern const uint8_t msyh_26px[];
extern const uint8_t msyh_28px[];
extern const uint8_t msyh_34px[];
#endif
