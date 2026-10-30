# epaper-panel · 书桌边的墨水屏投喂面板

ESP32-S3 + 7.5 寸黑白红墨水屏（GDEY075Z08 / UC8179，800×480 物理分辨率，**竖屏**显示）
组成的家庭内网投屏面板。手机连同一个 WiFi，浏览器打开面板的 IP 就能把内容投到墨水屏上。

- **课程表**：分天录入，每天上午/下午两栏，常驻显示
- **作文誊抄**：粘贴草稿 → 稿纸样式逐行排版，自动分页，三档字号
- **临时公告**：一行大字，随时覆盖显示

| 课程表实机照片 | 誊抄模式（左:iReader 右:本项目） |
|---|---|
| ![课程表实拍](docs/photos/timetable-real.jpg) | ![誊抄对比](docs/photos/scribe-vs-ereader.jpg) |

## 为什么要做这个

**起因是这两件小事。** 孩子抄好课程表贴在文具盒或书桌上，没几天就掉了、皱了；而且现在小学一周的课排得挺满，光科目就十几门，孩子一次次手抄既慢又容易抄错。打印出来当然清楚，但那张纸在家里同样会失踪——压在书堆下、夹在别的本子里，要找的时候永远找不到。

至于为什么不干脆买台打印机：家里打印场景其实不多，主要就是给孩子打打要誊抄的作文、打几页练习题。为这个买喷墨机，最怕的就是放久了堵喷头——一星期不打，用的时候准出问题；买激光机又犹豫，密闭房间里打印时那股味道实在算不上好，不想为了一个月一次的需求在家里添这么个东西。

后来在网上看到别人用墨水屏做的类似项目（这块屏最早就是拿来玩超市电子价签的），才反应过来：一块 7.5 寸墨水屏本来就够放一屏课程表，也够放一篇作文的誊抄稿——墨水屏常亮不耗电、不发光、不伤眼，正好像一块贴在书桌边的"纸"，而且内容随时能换，永远不会丢。于是借鉴了几个开源项目的经验，花了大半天时间，用 AI 把固件写了出来。

| 这块屏的"前世"：超市电子价签 |
|---|
| ![电子价签](docs/photos/hardware-origin.jpg) |

跑了一段时间，感觉还不错。买屏的时候没买好，选了黑白红**三色**屏，整屏刷新比双色屏慢（约 20 秒，见"刷新策略"）。好在后来发现了 UC8179 的黑白差分快刷通道：日常翻页、切模板、推送内容都只要 **1.6 秒**左右，只有定期清残影时才走一次整刷——日常等待已基本无感。

**接下来想做的**：3D 打印一个外壳，把主控和屏几块板子整合进一个像样的盒子里，再配一块小锂电池供电——不用拖着 Type-C 线，往书桌一角一放就能用，可用性会好很多。

## 界面

### 投喂主页 `GET /`

![投喂主页](docs/screenshots/web-home.png)

### 课程表录入 `GET /tt`（主页二级页）

![课程表录入](docs/screenshots/web-timetable.png)

### 墨水屏实际显示效果

| 课程表 | 作文誊抄 |
|---|---|
| ![课程表](docs/screenshots/screen-timetable.png) | ![誊抄](docs/screenshots/screen-scribe.png) |

## 硬件

| 项目 | 规格 |
|---|---|
| 主控 | ESP32-S3（带 PSRAM，WiFi 2.4G），装在**分立墨水屏转接板**上 |
| 屏幕 | MMK-E075A41 / GDEY075Z08，7.5 寸，800×480，黑/白/红三色（三色屏整屏刷新偏慢，见"已知限制"） |
| 驱动 | `GxEPD2_750c_GDEY075Z08`（UC8179），`setRotation(1)` → 逻辑 480×800 竖屏 |
| 接线 | 转接板自带升压电路与 24pin FPC 座，裸屏直插转接板；S3 主板只出 6 根信号线：`SCK=11 MOSI=10 CS=9 DC=8 RST=7 BUSY=6`（3V3/GND 由转接板供给） |
| 存储 | LittleFS（分区 app 12.5MB，见 `partitions.csv`） |
| 供电 | Type-C，**墨水屏刷新峰值电流较大，建议独立 2A 供电** |

## 固件编译与烧录

Arduino IDE / arduino-cli 打开 `firmware/epd_panel/epd_panel.ino`（**sketch 目录名必须保持 `epd_panel`**，Arduino 要求目录名与 ino 同名）。
库依赖：**GxEPD2**、**U8g2_for_Adafruit_GFX**、**ArduinoJson**、**ESPAsyncWebServer + ESPAsyncTCP-esynchronization**（Library Manager 安装即可）。

```bash
# 编译（自定义分区，app 12.5MB）
arduino-cli compile --fqbn esp32:esp32:esp32s3:FlashSize=16M,FlashMode=qio,PSRAM=opi,PartitionScheme=custom \
  firmware/epd_panel

# 编译 + 烧录一条龙（默认 COM6，可用 PORT=COM8 覆盖）
./tools/build_panel.sh          # 仅编译
./tools/build_panel.sh upload   # 编译并烧录
```

## 目录结构

```
firmware/epd_panel/        # Arduino sketch（目录名须与 ino 同名）
├── epd_panel.ino        # 主循环：WiFi 配网、HTTP 服务、渲染调度
├── api_panel.cpp/.h     # 投喂页 HTML 与 REST 接口
├── content_store.cpp/.h # LittleFS 存取 + JSON 兼容解析
├── render_panel.cpp/.h  # 排版与绘制（课程表 / 誊抄 / 公告）
├── panel_types.h        # 内部数据结构
├── fonts_ink.cpp/.h     # 中文字库（微软雅黑三档，u8g2 v1 格式，1.96MB）
└── partitions.csv       # 自定义分区（app 12.5MB）

docs/
├── photos/              # 实机照片（课程表 / 誊抄对比 / 电子价签前世）
├── hardware/            # 屏规格书与 24pin 针脚速查
└── screenshots/         # 投喂页截图与墨水屏渲染效果图

tools/
├── host_render.py       # 主机端像素级预览（烧录前先看效果，含分页复刻）
├── v1_verify.py         # u8g2 v1 字库解码器（预览与校验共用）
├── parse_cfont.py       # C 字库数组解析
├── gen_fonts_v1.py      # TTF → BDF → u8g2 v1 字库流水线
├── make_bdf.py          # Pillow 渲染位图 → BDF
├── font_verify_shipped.py # 直接校验固件字库产物（v1 解码像素级比对）
├── push_timetable.py    # 课程表 txt 一键推送（【周X】/上午：/下午：格式）
├── cadence_test.py      # 刷新节奏验证（串口同步，区分快刷/整刷波形）
├── reset_pulse.py       # DTR/RTS 硬复位 + 抓串口启动日志
├── patch_driver_reentry.py # 驱动补丁：partial-in 防残留（叠字根因修复，幂等）
├── patch_driver_clearbw.py # （历史）v3 刷白补丁 → 现为移除该补丁的还原脚本
├── build_panel.sh       # 编译 + 烧录脚本
└── shoot_web.sh         # 抓取投喂页截图
```

> 字库流水线还需要 u8g2 官方 `bdfconv.exe`（`gen_fonts_v1.py` 里 `U8G2` 常量指向其目录），
> 未随仓库分发；日常构建**不需要**重跑字库，`fonts_ink.cpp` 已预生成入库。

## 中文字库

`msyh.ttc`（微软雅黑，face index=0）→ PIL 4× 超采样渲染 → BDF → `bdfconv -f 1` → `fonts_ink.cpp`。
个人自用项目；要合法外发请换思源黑体 / Noto Sans CJK（OFL 许可），管线完全一致，只需换字体文件。

三档字号 **26 / 28 / 34 px**（阈值 110、build mode 2），advance 恒等于字号（等宽）。
誊抄默认 26px（小/中/大 = 26/28/34 可选），课程表固定 28px。

| 档位 | 压缩后大小 | 字数 |
|---|---|---|
| small (26px) | 577,837 B | 6881 |
| mid (28px) | 638,735 B | 6881 |
| big (34px) | 834,982 B | 6881 |

**u8g2 v1 格式硬限制**：单个字形压缩后必须 ≤255 字节。雅黑笔画比黑体密，
44px 档所有阈值/构建模式都超限无法生成，故大档封顶 34px（2026-10-28 定档）。
改字号后务必跑 `tools/font_verify_shipped.py` 校验固件产物，
并用 `tools/host_render.py` 做像素级预检，再烧录。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 投喂主页 |
| GET | `/tt` | 课程表录入页（二级页，自动回填） |
| POST | `/api/timetable` | 提交课程表 JSON |
| GET | `/api/timetable` | 读回当前课程表 JSON |
| POST | `/api/scribe` | 提交作文 `{title, text, font}` |
| GET | `/api/scribe` | 读回作文原文（调试用） |
| POST | `/api/display` | 显示临时公告 |
| POST | `/api/mode` | 切换模式：`timetable` / `scribe` / `notice` / `next` / `prev` / `refresh` |
| GET | `/api/status` | 当前状态（模式、页码、字号档、剩余堆、刷新计数器 `fast_count`/`full_in`） |

### 课程表 JSON

```json
{
  "title": "四 1 班课程表（游泳周）",
  "days": [
    { "name": "周一", "am": "语文、语文、数学、英语", "pm": "阅读、体育与健康、音乐、信息技术" }
  ]
}
```

同时兼容 `am`/`pm` 字段、数组式 `courses`、字符串式 `days` 等多种历史格式。

## 刷新策略（2026-10-30 实机定案：黑白差分快刷 + 定期整刷）

三色屏的"局刷"（`_Update_Part`，16~18s）并不快，但 UC8179 内嵌了一条
**黑白差分快刷**通道（Good Display 官方宣传点，GxEPD2 官方示例
`GxEPD2x_FastBlackWhiteOnColor` 就是这块屏，实测 **~1.5s**）。现在：

- **上电首刷 / 手动 `refresh` / 每 FAST_EVERY(=6) 次快刷** → 整刷
  （~20s），清残影并把两份屏 RAM 立为当前帧，重建干净的差分基准；
- **其余一切内容变化（翻页、切模板、推送）** → 黑白差分快刷：
  ① `writeImageToPrevious(上一帧)` 全屏回写基准 → ② `writeImageToCurrent(新帧)`
  → ③ `refresh_bw(0,0,800,480)` 差分驱动 → ④ 软件镜像滚动为下一帧的旧帧。
  全程不做 `_PowerOff`（差分波形靠电荷平衡维持像素）。
- **前提：画面全黑字**。红色不参与黑白差分，故渲染层已全线去红。
- `/api/status` 的 `fast_count` / `full_in` 报告"距下次自动整刷还有几次"。

### 三轮翻车复盘（差分快刷的坑，全部实机踩过）

1. **v1 窗口回写失步**：`displayWindowBW` 只把窗口内的像素回写旧帧 RAM，
   整屏换代时旧帧与屏面失步，差分把未更新像素再翻一次 → 新旧内容重叠。
2. **v3 前置刷白反噬**：想用"先刷白再差分"清残影，但差分后对屏 RAM 的
   任何全屏覆写都会抹掉刚立好的基准 → 白刷白、内容只进了旧帧通道 → 叠字。
3. **粘滞 partial-in（总根因）**：UC8179 的 0x91（partial-in）是带状态的，
   置位后**所有** RAM 写入被裁进最近的 0x90 窗口，直到 0x92 才解除。
   官方驱动 `_writeScreenBuffer` 的 0x91/0x92 被注释、`display(true)` 连写
   两笔 RAM 第二笔带残留窗口 → 一旦触发，"全屏"写实为窗口内写，屏 RAM 与
   软件镜像彻底失步，此后**怎么刷都在叠字、整刷也救不回**。
   修复见 `tools/patch_driver_reentry.py`（幂等补丁：`_writeScreenBuffer`
   进入先 0x92；`writeImageToPrevious` 追加全屏自闭合回写强制立正基准）。

同类开源项目（`yanyuandi/FastFreshBWOnColor`、ESP 组件
`cleishm/idfxx_epaper_uc8179`）与官方驱动注释的做法一致：禁红 + 差分 +
约 10 次局刷插一次整刷。差分残影无法根除，FAST_EVERY 是观感与速度的平衡点。

另注意：**整刷期间 HTTP 服务完全阻塞**（20 秒上下），客户端读超时是正常
现象，不是死机；脚本化测试请以串口 `display 完成` 日志为同步点
（参考 `tools/cadence_test.py`）。差分快刷只有 ~1.5s，无此问题。

## 已知限制

- 三色屏**整刷**约 20 秒（物理液晶翻转耗时，与 CPU 主频无关）；日常操作
  已走黑白差分快刷 ~1.5s，但快刷要求全黑字，**红色从此不可用**
  （数据模型保留 `day_red`/`cell_red` 字段，换 GDEY075T7 双色屏或接受
  红色降级即可恢复）
- 屏为 1-bit 红白黑三色（UC8179 只有黑/白 + 红/白两个 1-bit buffer），
  **不支持硬件灰度**；图片类需求建议服务端抖动（dithering）成 1-bit 点阵下发
- 差分快刷有轻微残影累积（欠驱动波形的物理代价），每 6 次快刷自动整刷
  压回；长期驻留深色内容后整刷也可能留轻微印
- **库依赖含两处本地补丁**（均在仓库内有幂等重放脚本，重装 GxEPD2 后需重跑）：
  `tools/patch_driver_reentry.py`（差分基准防残留，叠字根因修复）；
  `GxEPD2_3C.h` 的 `_black_buffer` 可见性宏补丁（`.ino` 首次 include 前
  `#define epd_panel_patched_public_buffer public:`，库原生构建零影响）
- 单页课程表容量 24 行（16 字/行），超出会自动分页
- 誊抄 26px 档每页 17×28 = 476 字，按**行数**而非字数分页
- 行首禁则已实现：标点不会落在行首，会把上一字挤到下一行
