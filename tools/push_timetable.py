# -*- coding: utf-8 -*-
"""课程表文本 → 面板推送工具。

文本格式（tools/课程表样例.txt 同款）：
    四 1 班课程表（游泳周）      <- 第一行 = 标题
    【周一】                     <- 天标题
    上午：语文、语文、数学、英语   <- 全角冒号；课程用「、」分隔
    下午：阅读、体健、音乐、信息技术

用法：
    python push_timetable.py [txt路径] [设备IP]
    （默认 tools/课程表样例.txt + http://192.168.31.62）

注意：推送成功后设备立即整刷（~28 秒），期间 HTTP 阻塞属正常。
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path


def parse(path):
    lines = [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    if not lines:
        raise SystemExit("空文件")
    title = lines[0]
    days, cur = [], None
    for ln in lines[1:]:
        m = re.match(r"^【(.+?)】$", ln)
        if m:
            cur = {"name": m.group(1), "am": "", "pm": ""}
            days.append(cur)
            continue
        m = re.match(r"^(上午|下午)[：:](.*)$", ln)
        if m and cur is not None:
            cur["am" if m.group(1) == "上午" else "pm"] = m.group(2).strip()
        else:
            raise SystemExit("无法解析行: %r" % ln)
    if not days:
        raise SystemExit("未找到【周X】天标题")
    return {"title": title, "days": days}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).parent / "课程表样例.txt")
    base = sys.argv[2] if len(sys.argv) > 2 else "http://192.168.31.62"
    payload = parse(src)
    print("标题: %s  天数: %d" % (payload["title"], len(payload["days"])))
    for d in payload["days"]:
        print("  %s 上午[%s] 下午[%s]" % (d["name"], d["am"], d["pm"]))

    req = urllib.request.Request(base + "/api/timetable",
                                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.loads(r.read().decode("utf-8"))
    print("API:", resp)
    if not resp.get("ok"):
        return 1

    # 等设备整刷完恢复响应（~28s）
    t0 = time.time()
    time.sleep(8)
    while time.time() - t0 < 90:
        try:
            with urllib.request.urlopen(base + "/api/status", timeout=6) as r:
                st = json.loads(r.read().decode("utf-8"))
            print("完成: mode=%s 课程表第%s/%s页"
                  % (st["mode"], st["tt_page"], st["tt_pages"]))
            return 0
        except Exception:                        # noqa: BLE001
            time.sleep(3)
    print("警告：90 秒内设备未恢复响应（可能仍在刷新，稍后看屏）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
