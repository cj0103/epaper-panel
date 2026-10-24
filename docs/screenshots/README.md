# 文档与截图

本目录存放 `epd_panel` 项目用于展示的界面截图。

## 投喂页截图（Web 端）

| 文件 | 内容 | 对应地址 |
|---|---|---|
| `web-home.png` | 投喂主页：当前状态卡片、课程表入口、作文推送表单、临时公告、模式切换 | `GET /` |
| `web-timetable.png` | 课程表录入二级页：表头标题 + 周一~周日 × 上午/下午 表单，自动回填已有内容 | `GET /tt` |

两张图均为移动端视口（390px 宽 @2x）下的真实设备页面截图。

### 复现方式

```bash
./tools/shoot_web.sh                # 默认设备 192.168.1.100
./tools/shoot_web.sh 192.168.1.50   # 指定其它设备 IP
```

脚本依赖 Windows 自带的 Edge（headless 模式），无需 Python；若检测到 Pillow 会自动裁掉底部空白。

> 两个注意点（踩过的坑）：
> 1. 必须传独立 `--user-data-dir`，否则 Edge 会复用已开着的实例并**静默跳过截图**（无报错、无文件）。
> 2. Edge 的 "bytes written" 提示走 **stderr**，脚本里要 `2>&1` 才能捕获并判断成功。

## 屏幕显示效果图（墨水屏）

| 文件 | 内容 |
|---|---|
| `screen-timetable.png` | 课程表页实际排版：标题 + 天标题红色独立成行 + 上午/下午内容顶格，单页装下 5 天共 23 行 |
| `screen-scribe.png` | 作文誊抄页实际排版：标题独占一行，正文逐行连续无空行，自动分页 |

这两张由主机端预览脚本 `tools/host_render.py` 生成，与固件渲染层像素级一致（同一套布局常量、同一个字库解码器），用于**烧录前**先在电脑上确认排版效果。

```bash
# 从设备真实数据生成
curl -s http://192.168.1.100/api/timetable -o tools/_tt_raw.json
python tools/host_render.py --timetable-json tools/_tt_raw.json

curl -s http://192.168.1.100/api/scribe -o tools/_scribe_raw.json
python tools/host_render.py --scribe tools/_scribe_body.txt
```
