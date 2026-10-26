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
#
# 用法：
#   ./build_panel.sh            # 仅编译
#   ./build_panel.sh upload     # 编译并烧录到 COM6
#   PORT=COM8 ./build_panel.sh upload
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/tools"

FQBN="esp32:esp32:esp32s3:FlashSize=16M,FlashMode=qio,PSRAM=opi,PartitionScheme=custom"
SKETCH="$ROOT/firmware/epd_panel"
BUILD="build-panel"
PORT="${PORT:-COM8}"

ACTION="build"
if [ "$1" = "upload" ]; then
  ACTION="upload"
  shift
fi

echo "[build] fqbn=$FQBN"
./arduino-cli compile --fqbn "$FQBN" --build-path "$BUILD" "$SKETCH"

if [ "$ACTION" = "upload" ]; then
  ESPTOOL="$(ls -1 "$HOME"/AppData/Local/Arduino15/packages/esp32/tools/esptool_py/*/esptool.exe 2>/dev/null | tail -1)"
  if [ -z "$ESPTOOL" ] || [ ! -f "$ESPTOOL" ]; then
    echo "[flash] 找不到 esptool.exe" >&2
    exit 1
  fi
  echo "[flash] 使用 $ESPTOOL 烧录到 $PORT ..."
  "$ESPTOOL" --chip esp32s3 --port "$PORT" --baud 921600 \
    --before default-reset --after hard-reset write-flash -z \
    --flash-mode keep --flash-freq keep --flash-size keep \
    0x0   "$BUILD/epd_panel.ino.bootloader.bin" \
    0x8000 "$BUILD/epd_panel.ino.partitions.bin" \
    0xe000 "$BUILD/boot_app0.bin" \
    0x10000 "$BUILD/epd_panel.ino.bin"
fi
