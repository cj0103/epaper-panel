#!/usr/bin/env bash
# 抓取设备投喂页截图（供 README / 仓库使用）
#
# 用法:
#   ./tools/shoot_web.sh [设备IP] [输出目录]
#
# 默认设备 IP 192.168.1.100，输出到 docs/screenshots/
#
# 依赖: Edge（Windows 自带）headless 截图，无需 Python。
# 可选: 若装有 Pillow（python -c "import PIL"），会自动裁掉底部空白。
#
# 注意: 必须使用独立 --user-data-dir，否则 Edge 会复用已开着的实例而静默跳过截图。

set -euo pipefail

# 用脚本自身位置定位项目根（不能用 $0 相对路径：调用方 cwd 可能不同）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

IP="${1:-192.168.1.100}"
OUT="${2:-$ROOT/docs/screenshots}"

EDGE="${EDGE_BIN:-/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe}"
[ -f "$EDGE" ] || { echo "找不到 Edge，可用 EDGE_BIN 环境变量指定路径"; exit 1; }

mkdir -p "$OUT"
OUT_WIN="$(cygpath -w "$OUT")"
PROFILE_WIN="$(cygpath -w "${TMPDIR:-/tmp}/edge_shot_profile")"

shot() {
  local url="$1" file="$2" height="$3"
  echo ">> $url  ->  $file"
  # 注意: Edge 的 "bytes written" 提示输出在 stderr，必须 2>&1 才能捕获
  "$EDGE" --headless --disable-gpu --no-sandbox --hide-scrollbars \
          --force-device-scale-factor=2 --window-size=390,"$height" \
          --virtual-time-budget=8000 --user-data-dir="$PROFILE_WIN" \
          --screenshot="$OUT_WIN\\$file" "$url" 2>&1 | grep -i "written" || {
    echo "   !! 截图失败：$file"; return 1
  }
}

# 投喂主页（状态卡片 / 课程表入口 / 作文表单 / 公告 / 模式）
shot "http://$IP/"   "web-home.png"     2000
# 课程表录入二级页（分天录入，自动回填）
shot "http://$IP/tt" "web-timetable.png" 1900

# 可选：裁掉底部空白
PY=""
for c in python3 python "E:/software/python311/python"; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import PIL" >/dev/null 2>&1; then PY="$c"; break; fi
  if [ -x "$c" ] && "$c" -c "import PIL" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -n "$PY" ]; then
  "$PY" - "$OUT" <<'PYEOF'
import sys
from PIL import Image
out = sys.argv[1]
BG = (245, 246, 248)
for f in ("web-home.png", "web-timetable.png"):
    p = out + "/" + f
    im = Image.open(p).convert("RGB")
    w, h = im.size
    px = im.load()
    last = 0
    for y in range(h - 1, -1, -1):
        row = [px[x, y] for x in range(0, w, 7)]
        if any(abs(c[0]-BG[0]) + abs(c[1]-BG[1]) + abs(c[2]-BG[2]) > 18 for c in row):
            last = y
            break
    im.crop((0, 0, w, min(h, last + 28))).save(p)
    print("裁剪 %s -> %s" % (f, im.crop((0, 0, w, min(h, last + 28))).size))
PYEOF
else
  echo "(未找到 Pillow，跳过底部裁剪)"
fi

echo
echo "完成，输出目录: $OUT"
ls -la "$OUT"
