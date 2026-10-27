/* 接线自动诊断：在候选引脚组合上逐个尝试，检测屏是否有 SPI 应答
 *
 * 用法：烧录后看串口输出。会依次尝试若干种常见接法，
 * 任何一种能让 Get Status 读回非 0x00/0xFF 的值，就是接对了。
 *
 * 覆盖的候选：
 *   A) 当前固件设定：SCK11 MOSI10 CS9 DC8 RST7 BUSY6（老转接板 + S3 主板）
 *   B) iDevice 整合板：SCK12 MOSI11 CS10 DC13 RST14 BUSY15
 *   C) 交换 MOSI/CS：SCK11 MOSI9 CS10 DC8 RST7 BUSY6
 *   D) 只换 CS/DC：SCK11 MOSI10 CS8 DC9 RST7 BUSY6
 *   E) RST 换 5：SCK11 MOSI10 CS9 DC8 RST5 BUSY6
 *   F) BUSY 换 4：SCK11 MOSI10 CS9 DC8 RST7 BUSY4
 */
#include "epd_probe.h"
#include <SPI.h>

struct PinSet {
  const char* name;
  int sck, mosi, cs, dc, rst, busy;
};

static const PinSet candidates[] = {
  {"A 当前设定   SCK11/MOSI10/CS9/DC8/RST7/BUSY6",      11, 10,  9,  8,  7,  6},
  {"B iDevice板  SCK12/MOSI11/CS10/DC13/RST14/BUSY15", 12, 11, 10, 13, 14, 15},
  {"C 换MOSI/CS  SCK11/MOSI9/CS10/DC8/RST7/BUSY6",      11,  9, 10,  8,  7,  6},
  {"D 换CS/DC    SCK11/MOSI10/CS8/DC9/RST7/BUSY6",      11, 10,  8,  9,  7,  6},
  {"E 换RST      SCK11/MOSI10/CS9/DC8/RST5/BUSY6",      11, 10,  9,  8,  5,  6},
  {"F 换BUSY     SCK11/MOSI10/CS9/DC8/RST7/BUSY4",      11, 10,  9,  8,  7,  4},
};

/* 单次尝试：按给定引脚接线，返回读到的 status（0x00/0xFF 表示无应答） */
static uint8_t tryPins(int sck, int mosi, int cs, int dc, int rst, int busy) {
  // 复位这些脚
  pinMode(rst, OUTPUT); digitalWrite(rst, LOW);
  pinMode(cs, OUTPUT);  digitalWrite(cs, HIGH);
  pinMode(dc, OUTPUT);  digitalWrite(dc, HIGH);
  pinMode(busy, INPUT_PULLDOWN);

  SPI.begin(sck, -1, mosi, cs);
  SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));

  // 硬复位
  digitalWrite(rst, LOW);  delay(30);
  digitalWrite(rst, HIGH); delay(30);
  digitalWrite(rst, LOW);  delay(30);
  digitalWrite(rst, HIGH); delay(200);

  // Power On
  digitalWrite(cs, LOW);
  SPI.transfer(0x04);
  digitalWrite(cs, HIGH);

  // 等 BUSY 释放（最多 1.5s）
  uint32_t t0 = millis();
  while (millis() - t0 < 1500 && digitalRead(busy) == LOW) delay(10);

  // Get Status (0x71 | 0x80)
  digitalWrite(cs, LOW);
  SPI.transfer(0xF1);
  uint8_t st = SPI.transfer(0x00);
  digitalWrite(cs, HIGH);

  SPI.endTransaction();
  return st;
}

void epdProbe() {
  Serial.println();
  Serial.println("====== 接线自动诊断 ======");
  Serial.println("依次尝试各组引脚，读取 Get Status；读到非 0x00/0xFF 即为接对");
  Serial.println();

  for (const PinSet& p : candidates) {
    Serial.printf("[试] %s\n", p.name);
    uint8_t st = tryPins(p.sck, p.mosi, p.cs, p.dc, p.rst, p.busy);
    Serial.printf("     → Get Status = 0x%02X  %s\n", st,
                  (st == 0x00 || st == 0xFF) ? "无应答" : "★ 有应答！接线正确");
    delay(300);
  }
  Serial.println();
  Serial.println("====== 诊断结束 ======");
  Serial.println();
}
