// 字库自检探针：只做串口测量，不往屏幕写像素
//
// 用途：确认 u8g2 桥接层能正确解析内置的 v1 字库（字形可查到、宽度合理）。
// 注意：这里用独立实例，不碰渲染层的 u8g2Fonts（setup 中本函数先于
// u8g2Fonts.begin(display) 调用）。
//
// 宽度口径提醒：getUTF8Width 返回的是**墨迹像素宽**（末字换成 glyph_width
// 再加 glyph_x_offset），不是 advance。本字库 advance 恒等于字号，
// 44px 档各字墨迹宽差异很大（'课'40 / 'A'20 / '!'5）属正常现象。
#include "render_panel.h"
#include "fonts_ink.h"

static U8G2_FOR_ADAFRUIT_GFX g_probe;

void fontProbe() {
  g_probe.begin(display);

  static const char* probe[] = {"A", "0", "a", "!", "课", "程", "表", "，", "。"};
  g_probe.setFont(zhhei_34px);
  Serial.println("[自检] 字库测量 (34px):");
  for (auto s : probe) {
    Serial.print("[自检]   '"); Serial.print(s);
    Serial.print("' 墨迹宽="); Serial.print(g_probe.getUTF8Width(s));
    Serial.println();
  }
  g_probe.setFont(zhhei_28px);
  Serial.print("[自检] 28px '课' 墨迹宽=");
  Serial.println(g_probe.getUTF8Width("课"));
  g_probe.setFont(zhhei_44px);
  Serial.print("[自检] 44px '课' 墨迹宽=");
  Serial.println(g_probe.getUTF8Width("课"));
  Serial.println("[自检] 字库 OK");
}
