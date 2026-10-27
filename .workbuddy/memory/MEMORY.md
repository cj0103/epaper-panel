# epaper-panel 项目长期记忆

## 项目定位
7.5 寸墨水屏内网投屏面板：课程表 / 作文誊抄 / 临时公告。手机浏览器投喂，断电保留。
仓库：https://github.com/cj0103/epaper-panel

## 硬件演进（重要）

### v1：分立驱动板 + ESP32-S3（旧板，已验证可点亮）
- 接线：SCK=11 MOSI=10 CS=9 DC=8 RST=7 BUSY=6
- 2026-10-25 验证：能正常点亮并跑通固件

### v2：iDevice 整合驱动板（ESP32-S3 N16R8，**2026-10-27 已退回弃用**）
- 接线：SCK=12 MOSI=11 CS=10 DC=13 RST=14 BUSY=15（取自原厂 Python 示例）
- 3.3V/GND 板内直连，只接 6 根信号线
- **原生 USB**（无 USB-UART 桥）→ 必须 `CDCOnBoot=cdc`
- 屏接口丝印 `epaper 2.13br`：原厂按 **2.13 寸三色屏（EPD213R）** 设计
- ⚠️ **该板 + 7.5 寸裸屏 = 硬件不兼容，已定案**：板座 24 针是下接、屏是上接，
  针序镜像导致屏 VDD(16) 落在板脚 GND(16) 或 BUSY(9)，两种插法都拿不到 3.3V；
  且板座缺 RESE/GDR/VGH/VGL 外部供电与去耦。软件侧 15 组控制器×SPI 全灭已排除协议因素。
  **现在用的是 v1 老方案（v1 才是当前在用）。**

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
PartitionScheme=custom,UploadMode=default
```
- 老方案主板自带 USB-UART 桥 → Serial 走 UART0，**不要**加 `USBMode=hwcdc,CDCOnBoot=cdc`
- 原生 USB 板才需要，`./tools/build_panel.sh` 用 `SERIAL_CDC=1` 开关追加

## 存储层约定
- 分区表 `firmware/epd_panel/partitions.csv`：
  app0 0x10000/0xC80000、spiffs 0xC90000/0x360000、coredump 0xFF0000/0x10000
  （spiffs 与 coredump 不可重叠，esp_pt 会静默收缩导致超级块几何不匹配）
- **分区几何指纹**：EEPROM 0..11 字节存 magic('LFSG')+分区偏移+大小。
  与当前几何不一致 → 先整块擦除 spiffs 分区，再挂载。
  原因：core 的 `LittleFS.begin()` 把 `grow_on_mount` 写死为 true，
  几何一变就触发 `assert failed: lfs_fs_grow_ lfs.c:5272`。
  挂载必须走 core 标准路径（core 的 begin 才会绑定 mountpoint），
  见 `content_store.cpp` 的 `mountLittleFS()`。

## 诊断工具
- `firmware/epd_panel/epd_probe.cpp`：屏链路自检（Get Status 判 SPI 通断 + BUSY 极性）
- `epd_panel.ino` 里 `DIAG_MODE` 开关：0=完整 / 1=心跳 / 2=屏探针
- `tools/build_panel.sh`：arduino-cli 自动查找 + `--after watchdog-reset`，
  `PORT=COMx` 覆盖串口；仓库无独立抓串口脚本，必要时临时写

## 技术文档（已入库 docs/hardware/）
- `HINK-E075A42-Spec-A1.pdf`（合力泰官方规格书，本屏来源）
- `GDEY075Z08-Spec.pdf`（佳显同款 24pin，AES 加密空口令可开）
- `UC8179-24pin-pinout.md`：两份规格书逐字核对的针脚速查表
- `README.md`：当前方案 / 已弃用 iDevice 方案（含失败原因）/ 24pin 标准针序

## 烧录备忘
- COM 口会漂移（COM8↔COM9），先 `serial.tools.list_ports` 确认
- 读日志必须 `dsrdtr=False` 且开端口后立即 `dtr=False; rts=False`
- 仓库副本没有 arduino-cli.exe，借用 `../../2026-10-22-19-44-10/tools/arduino-cli.exe`
