# 硬件参考

## 当前方案：分立转接板 + ESP32-S3 主板（2026-10-27 恢复）

- **屏**：MMK-E075A41 / GDEY075Z08，7.5 寸，800×480，黑/白/红三色，主控 **UC8179**
- **驱动**：`GxEPD2_750c_GDEY075Z08`（GxEPD2 1.6.9，`src/gdey3c/`）
  ⚠️ 不要用 `GxEPD2_750c_GDEW075Z08`（`src/epd3c/`，GD7965 主控）——
  命令集看着像，但初始化参数、波形表、OTP 处理不同，用错会"能通信但不刷新/花屏"。
- **接线（S3 主板 → 转接板 6 根信号线）**：

  | 信号 | GPIO |
  |------|------|
  | SCK  | 11 |
  | MOSI | 10 |
  | CS   | 9  |
  | DC   | 8  |
  | RST  | 7  |
  | BUSY | 6  |

  3V3 / GND 由转接板供给，不占主板 GPIO。
- **BUSY 极性**：LOW = 忙，HIGH = 空闲。固件里 `pinMode(EPD_BUSY, INPUT)`，
  且必须放在 `display.init()` **之后**（GxEPD2 的 init 会把它改成 INPUT_PULLUP）。
- **串口**：这块分立板自带 USB-UART 桥芯片，Arduino 的 Serial 走 UART0(GPIO43/44)，
  编译时**不要**加 `CDCOnBoot=cdc`。烧录用 `tools/build_panel.sh`，
  串口按实际枚举指定：`PORT=COM9 ./build_panel.sh upload`。

## 已弃用：iDevice 墨水屏整合驱动板（ESP32-S3 版）

2026-10-26 短暂换用该板，2026-10-27 已退回。参考资料留档：

- `idevice-s3-schematic.png` — PCB 布线图（作者标为"原理图"，实为 PCB layout）
- `idevice-s3-pcb.png` — PCB 布线图（另一视角）

来源：https://blog.csdn.net/jetmie/article/details/157909899

### 该板的针脚

`SCK=12 MOSI=11 CS=10 DC=13 RST=14 BUSY=15`
（对应作者 Python 示例 `EPD213R(12, 11, 10, 13, 14, 15)`）。
该板按 **2.13 寸三色屏（EPD213R）** 设计，屏接口丝印 `epaper 2.13br`。

### 为什么 7.5 寸裸屏插不上（重要教训）

该板 24pin FPC 座的网络为：

```
1 NC / 2 GDR / 3 RESE / 4-7 NC / 8 GND / 9 BUSY / 10 RST / 11 DC / 12 CS /
13 SCLK / 14 SDI / 15 3V3 / 16 GND / 17 GND / 18 NC / 19 NC / 20 PREVGH /
21 NC / 22 PREVGL / 23 NC / 24 NC
```

而 7.5 寸 UC8179 屏的 24pin 定义是：
`15 VDDIO / 16 VDD(芯片主电源) / 17 GND / 18 VDDD / 20 VDH / 21 VGH / 22 VDL / 23 VGL / 24 VCOM`

两条对不上：

1. **电源脚错位**——屏的 VDD(16) 必须 3.3V，板座 16 脚是 GND → 主电源被短接地；
   即使把针序镜像（面板脚 N ↔ 座脚 25-N），VDD 也会落到板脚 9（BUSY）→ 依然无电。
2. **上接 / 下接不匹配**——板座是"下接"，7.5 寸屏是"上接"。翻面 180° 插入是
   **镜像**不是旋转，针号会左右互换（面板 1 号脚压到座子 24 号脚），
   触点虽然导通，信号仍然错位。

另外 UC8179 7.5 寸屏还要求：RESE(3) 外接电流采样电阻、GDR(2) 外接 N-MOS、
21 VGH / 23 VGL 外部供电、20~24 去耦电容——这些板座都没提供。

**结论：整合板 + 7.5 寸裸屏在硬件层就不兼容，不是固件问题。**
（实测现象：BUSY 恒为"浮空"——上拉读高、下拉读低，谁都不驱动；
GET STATUS 只回总线静态电平；控制器 × SPI 联合扫描 15/15 全灭。）

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
- pin 8 = BS，低电平 = 4 线 SPI，高电平 = 3 线 9bit SPI。
