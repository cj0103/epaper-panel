#!/usr/bin/env bash
# epd_panel 构建 / 烧录脚本
#
# 关键点：
#   1. fqbn 必须用 PartitionScheme=custom —— 自定义分区表放在 sketch 目录下的
#      partitions.csv（app 12.5MB / spiffs 3.375MB），core 的 prebuild hook 会
#      自动拷进 build 目录。用官方 app3M_fat9M_16MB（3MB app）装不下 2.41MB
#      字库 + 1.09MB 代码。
#      注：custom 的 upload.maximum_size 报的是 16MB，arduino-cli 的
#      "Sketch uses xx%" 因此偏乐观，实际以 partitions.csv 为准。
#   2. 字库已预生成并写入 fonts_ink.cpp，日常构建不需要跑字库流水线；
#      只有改字号/字符集才需要重跑 tools/gen_fonts_v1.py。
#   3. 烧录不走 arduino-cli upload：core 3.3.10-cn 的 tools/flasher.exe 缺失
#      （PyInstaller 打包件），改为直接调 esptool.py 目录下的 esptool.exe。
#   4. 串口通道取决于主板：老分立板自带 USB-UART 桥芯片 → Serial 走 UART0(GPIO43/44)，
#      必须保持默认 CDCOnBoot（关闭）；换没有桥芯片的原生 USB 板（iDevice 整合板）
#      时要追加 USBMode=hwcdc,CDCOnBoot=cdc，否则 app 段日志全部丢失（只剩 ROM 日志）。
#      用 SERIAL_CDC=1 开关切换，见下面 FQBN。
#
# 用法：
#   ./build_panel.sh            # 仅编译
#   ./build_panel.sh upload     # 编译并烧录到 COM6
#   PORT=COM9 ./build_panel.sh upload        # 指定串口
#   SERIAL_CDC=1 ./build_panel.sh upload     # 原生 USB 板（无桥芯片）才需要
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/tools"

FQBN="esp32:esp32:esp32s3:FlashSize=16M,FlashMode=qio,PSRAM=opi,PartitionScheme=custom,UploadMode=default"
# 原生 USB 板（iDevice 整合板那类，没有 USB-UART 桥）才追加这两个参数
if [ "${SERIAL_CDC:-0}" = "1" ]; then
  FQBN="$FQBN,USBMode=hwcdc,CDCOnBoot=cdc"
fi
# SKETCH / BUILD 可用环境变量覆盖：默认编译正式固件
SKETCH="${SKETCH:-$ROOT/firmware/epd_panel}"
BUILD="${BUILD:-build-panel}"
PORT="${PORT:-COM6}"

ACTION="build"
if [ "$1" = "upload" ]; then
  ACTION="upload"
  shift
fi

echo "[build] fqbn=$FQBN"
# arduino-cli 可能不在 PATH：从几个常见位置找
CLI=""
for cand in \
  "$ROOT/tools/arduino-cli.exe" \
  "$(ls -1 "$HOME"/WorkBuddy/*/tools/arduino-cli.exe 2>/dev/null | tail -1)" \
  "$(command -v arduino-cli 2>/dev/null)"; do
  if [ -n "$cand" ] && [ -x "$cand" ]; then CLI="$cand"; break; fi
done
if [ -z "$CLI" ]; then
  echo "[build] 找不到 arduino-cli，请手动安装或放到 tools/ 下" >&2
  exit 1
fi
echo "[build] arduino-cli = $CLI"
"$CLI" compile --fqbn "$FQBN" --build-path "$BUILD" "$SKETCH"

if [ "$ACTION" = "upload" ]; then
  ESPTOOL="$(ls -1 "$HOME"/AppData/Local/Arduino15/packages/esp32/tools/esptool_py/*/esptool.exe 2>/dev/null | tail -1)"
  if [ -z "$ESPTOOL" ] || [ ! -f "$ESPTOOL" ]; then
    echo "[flash] 找不到 esptool.exe" >&2
    exit 1
  fi
  echo "[flash] 使用 $ESPTOOL 烧录到 $PORT ..."
  # ★ --after 必须用 watchdog-reset，不能用 hard-reset：
  #   ESP32-S3 原生 USB（USB Serial/JTAG，VID:PID=303A:1001）没有 USB-UART 桥，
  #   hard-reset 走的是 USB_UART_CHIP_RESET，ROM 一律判成 boot:0x0 DOWNLOAD，
  #   板子会停在 "waiting for download" 永远跑不起应用。
  #   watchdog-reset 是内核复位，ROM 会重新采样 GPIO0 引导脚 → 正常启动进应用。
  #   带 USB-UART 桥的老分立板两种都行，用 watchdog-reset 更稳。
  SKETCH_NAME="$(basename "$SKETCH")"
  "$ESPTOOL" --chip esp32s3 --port "$PORT" --baud 921600 \
    --before default-reset --after watchdog-reset write-flash -z \
    --flash-mode keep --flash-freq keep --flash-size keep \
    0x0   "$BUILD/$SKETCH_NAME.ino.bootloader.bin" \
    0x8000 "$BUILD/$SKETCH_NAME.ino.partitions.bin" \
    0xe000 "$BUILD/boot_app0.bin" \
    0x10000 "$BUILD/$SKETCH_NAME.ino.bin"
fi
