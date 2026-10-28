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
- **不支持灰度（2026-10-28 调查定案）**：UC8179 只有 0x10(黑/白)+0x13(红/白)两个
  1-bit buffer；驱动 lut_20~25 全是 partial update LUT（非灰度 LUT），GxEPD2 无灰度接口。
  同尺寸想要 16 灰度 = 换黑白屏 GDEY075T7。伪灰度可软件 dithering（1-bit 网点模拟）。

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

## 字库（v1 格式）关键事实
- 管线：Pillow 渲染（4× 超采样 → LANCZOS → 阈值二值化）→ BDF → **官方 `bdfconv -f 1`**
  → `fonts_ink.cpp`。`bdfconv.exe` 已放进仓库 `tools/u8g2tools/`（gitignore 内）。
- **u8g2 v1 单字形硬上限 255B**（字形项 = 编码2B + 尺寸1B + 位流N B），
  超过就 `RLE Compress: Error, glyph too large`，**整个字库生成失败**。
- BDF 里 `DWIDTH` 固定 px、`SWIDTH = px*1000/8` → advance 恒等于字号（等宽）。
- 空格不入字库（渲染层按 px 补位）。
- 体积口径：`.c` 是八进制转义源码，比二进制**虚高 ~2.8 倍**，
  量体积必须用 `parse_c_font` 还原二进制再量。
- build mode：0=最紧凑 / 1=统一字高 / 2=统一字宽 / 3=宽高取 8 的倍数。

## 字体选型（2026-10-28 定档，尚未实施）
- 目标字体：微软雅黑 `C:\Windows\Fonts\msyh.ttc`（TTC，face index=0）
- **★ 用户最终拍板：字号档 = 26 / 28 / 34**（三档 thr=110 build=2 全部可行，
  实测体积比黑体同档 +2.8%~+3.4%）。彻底绕开雅黑 44px 的 255B 上限问题。
  落地时大档 44→34：誊抄正文 `cols` 10→12、`rows` 16→20（每页 160→240 字）。
- 存档：雅黑 44px 不可行（v1 单字形 255B 上限必爆，所有阈值/build mode 都不行）；
  42px/thr180/build0 可行（1,038,068B）——若将来想恢复大标题档可走 42px。
- v1 解码已用 `v1_verify.Decoder` 像素级验证通过（advance 仍=字号，等宽）。
- 需同步改动点：`make_bdf.py` FONT_FILE / `gen_fonts_v1.py` SIZES(44→42) 与符号名
  (`zhhei_*px`→`msyh_*px`) / `render_panel.cpp:283,289` / `api_panel.cpp:50` 网页文案 /
  `host_render.py` 的 `Font("zhhei_%dpx")` 三处
- ⚠️ 许可：`simhei.ttf` 与 `msyh.ttc` 同为 Windows 商业字体，
  位图字库进公开仓库有外发风险；要可合法外发应改用思源黑体 / Noto Sans CJK (OFL)，
  管线完全一致，只需换字体文件。

## 待修 Bug 清单（2026-10-28 审查，已定位未动手）
- **P0** `epd_panel.ino:95` `display.display(g_hard_refresh)` 语义反了：
  GxEPD2 的 `display(bool)` 是 `partial_update_mode`，**`true`=快刷、`false`=整刷**，
  与注释相反；连带 `epd_panel.ino:213-215` 的 4 次计数和
  `api_panel.cpp:290,299` 的首末页整刷判断一起反向。
- **P0** `render_panel.cpp:351-357` `scribeBuildRows` 行号用 `uint8_t`，
  255 处回绕 → 正文 >4080 汉字（28px 档）必然错乱（页数算错、正文截断）。
- **P1** `epd_probe.cpp` 每组候选不 `SPI.end()` → 探针引脚不切换，对照失效。
- **P1** `portal_impl.cpp` 密码只存 32B（WPA2 上限 63）→ 长密码读不回来连不上；
  SSID/密码写入无长度校验。
- **P1** `portal_impl.cpp:58` `urlDecode()` 只认固定大写 `%XX`，
  中文 SSID 断链（core WebServer **不**做解码，这层必须自己写对）。
- **P1** `api_panel.cpp:323-333` JSON 只转义 `"` `\` `\n`，漏 `\r` `\t` → 非法 JSON。
- **P2** API 无请求体长度上限；`tt.days/tt.periods` 先截断后校验；
  `DynamicJsonDocument` 在 ArduinoJson 7.4.3 已废弃（且 v7 内存池动态增长，
  容量参数被忽略）；`ssidList` 重复累积。
- 已验证**没问题**别误改：SPI 实际 4MHz（GxEPD2 构造里 `_spi_settings(4000000,...)`）；
  固件先 `SPI.begin(自定义引脚)` 不会被 GxEPD2 覆盖（core `if(_spi) return`）；
  core 3.3.10 的 `begin()` 不调 `spiAttachSS` 故 CS 手动控制无冲突；
  红/黑/白三色通路完好（`fg_color` 是 uint16_t，0xF800 不截断）。
