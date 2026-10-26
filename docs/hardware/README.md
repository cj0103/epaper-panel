# 硬件参考图

iDevice 墨水屏驱动板（ESP32-S3 版）原厂资料，从作者博客下载：

- `idevice-s3-schematic.png` — PCB 布线图（作者标为"原理图"，实为 PCB layout）
- `idevice-s3-pcb.png` — PCB 布线图（另一视角）

来源：https://blog.csdn.net/jetmie/article/details/157909899

## 关键信息

- **ESP32-S3 针脚**：SCK=12 MOSI=11 CS=10 DC=13 RST=14 BUSY=15
  （对应作者 Python 示例 `EPD213R(12, 11, 10, 13, 14, 15)`）
- **屏接口丝印**：`epaper 2.13br` —— 原厂按 **2.13 寸三色屏（EPD213R）** 设计，
  不是 7.5 寸。7.5 寸裸屏（24pin FPC）需要额外的升压驱动电路。
- **升压电阻**：板载 0.47Ω（三色）/ 3Ω（双色）可选，对应屏的驱动电压需求。

## 24pin FPC 标准针序（UC8179 7.5" 800x480 三色）

| Pin | 信号 | Pin | 信号 |
|-----|------|-----|------|
| 1 | NC | 13 | **SCL (SCK)** |
| 2 | GDR | 14 | **SDA (MOSI)** |
| 3 | RESE | 15 | VDDIO |
| 4 | NC | 16 | VCI |
| 5 | VSHR | 17 | VSS (GND) |
| 6 | TSCL | 18 | VDD |
| 7 | TSDA | 19 | VPP |
| 8 | BS | 20 | VSH |
| 9 | **BUSYN** | 21 | VGH |
| 10 | **RSTN** | 22 | VSL |
| 11 | **D/C** | 23 | VGL |
| 12 | **CSB** | 24 | VCOM |

要点：
- **BUSYN 为 active-LOW**（低=刷新中，高=空闲），与 GxEPD2 的 `busy_level=LOW` 一致。
- pin 2/3/5/8 是升压电路控制脚（GDR/RESE/VSHR/BS），裸屏必须配驱动板。
- pin 6/7 是 I²C 温度传感器（TSCL/TSDA）。
