# epaper-panel 项目长期记忆

## 项目定位
7.5 寸墨水屏内网投屏面板：课程表 / 作文誊抄 / 临时公告。手机浏览器投喂，断电保留。
仓库：https://github.com/cj0103/epaper-panel

## 硬件演进（重要）

### v1：分立驱动板 + ESP32-S3（旧板，已验证可点亮）
- 接线：SCK=11 MOSI=10 CS=9 DC=8 RST=7 BUSY=6
- 2026-10-25 验证：能正常点亮并跑通固件

### v2：iDevice 整合驱动板（ESP32-S3 N16R8，当前）
- 接线：SCK=12 MOSI=11 CS=10 DC=13 RST=14 BUSY=15（取自原厂 Python 示例）
- 3.3V/GND 板内直连，只接 6 根信号线
- **原生 USB**（无 USB-UART 桥）→ 必须 `CDCOnBoot=cdc`
- 屏接口丝印 `epaper 2.13br`：原厂按 **2.13 寸三色屏（EPD213R）** 设计
- 板载升压电阻：0.47Ω（三色）/ 3Ω（双色）可选
- ⚠️ 7.5 寸裸屏（24pin FPC）插上去不工作：升压电路控制脚(GDR/RESE/VSHR/BS)
  与高压输出(VGH/VGL/VCOM) 对不上，见 docs/hardware/README.md

## 屏
- 型号：盒马 7.5 寸红白黑三色价签屏，800×480，**主控 UC8179**
- 驱动类：`GxEPD2_750c_GDEY075Z08`（gdey3c 目录，GxEPD2 1.6.9）
  - 旧代码误用 `GxEPD2_750c_GDEW075Z08`（GD7965）
  - 换驱动时 `render_panel.h` 的 extern 声明必须同步改
- BUSY 为 active-LOW（低=忙），与 GxEPD2 `busy_level=LOW` 一致
- 竖屏使用：rotation=1（逻辑 480×800）

## 编译参数（固定）
```
esp32:esp32:esp32s3:FlashSize=16M,FlashMode=qio,PSRAM=opi,
PartitionScheme=custom,USBMode=hwcdc,CDCOnBoot=cdc,UploadMode=default
```

## 存储层约定
- 分区表 `firmware/epd_panel/partitions.csv`：
  app0 0x10000/0xC80000、spiffs 0xC90000/0x350000、coredump 0xFE0000/0x10000
  （spiffs 与 coredump 不可重叠，esp_pt 会静默收缩导致超级块几何不匹配）
- **不用 Arduino 的 `LittleFS.begin()`**：其内部 `grow_on_mount=true` 会触发
  `lfs_fs_grow_` assert。用 `esp_vfs_littlefs_register` 自行挂载，`grow_on_mount=false`，
  失败则擦分区重挂。见 `content_store.cpp` 的 `mountLittleFS()`

## 诊断工具
- `firmware/epd_panel/epd_probe.cpp`：屏链路自检（Get Status 判 SPI 通断 + BUSY 极性）
- `epd_panel.ino` 里 `DIAG_MODE` 开关：0=完整 / 1=心跳 / 2=屏探针
- `tools/cap.py`：容错串口抓取（端口重枚举自动重开）

## 烧录备忘
- COM 口会漂移（COM8↔COM9），先 `serial.tools.list_ports` 确认
- 读日志必须 `dsrdtr=False` 且开端口后立即 `dtr=False; rts=False`
- 仓库副本没有 arduino-cli.exe，借用 `../../2026-10-22-19-44-10/tools/arduino-cli.exe`
