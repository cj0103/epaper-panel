# -*- coding: utf-8 -*-
"""刷新节奏验证：翻页/切模式走快刷，连续 4 次快刷后自动转整刷。

设备一次渲染要 19~27 秒且期间 HTTP 会读超时，因此所有步骤都以
"串口 display 完成" 为同步点；push 内容只在第 0 步做一次（之后内容不变，
用翻页/切模式来触发"画面变化但幅度小"的快刷场景）。

★ 关键：设备渲染期间仍可能先回 HTTP 响应（sendOk 先于刷屏）。若 POST 秒回，
必须再等一次 display 完成，否则下一轮会错位到"渲染中"，测到的是上一次
刷新的波形。wait_pair 处理了这个竞态。
"""
import json
import sys
import time
import urllib.request

import serial

BASE = "http://192.168.31.62"
PORT = sys.argv[1] if len(sys.argv) > 1 else "COM6"

# 长文：26px 档 17列x28行=476字/页，保证多页可翻
LONG = ("长文翻页测试第一段。" + "一二三四五六七八九十" * 12)


def post(path, body, ct="application/json", timeout=12):
    req = urllib.request.Request(BASE + path, data=body.encode("utf-8"),
                                 headers={"Content-Type": ct}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), True
    except Exception:                            # noqa: BLE001
        return None, False


class Ser(object):
    def __init__(self, port):
        self.s = serial.Serial(port, 115200, timeout=0.5, dsrdtr=False)
        self.s.dtr = False
        self.s.rts = False
        self.buf = b""

    def pump(self, seconds=1.0):
        t0 = time.time()
        while time.time() - t0 < seconds:
            self.s.read(4096)

    def wait_display(self, timeout=120):
        """返回本次 display 的波形标记列表（PARTIAL/FULL + _Update_*）"""
        t0 = time.time()
        marks = []
        while time.time() - t0 < timeout:
            chunk = self.s.read(2048)
            if not chunk:
                continue
            self.buf += chunk
            while b"\n" in self.buf:
                ln, self.buf = self.buf.split(b"\n", 1)
                ln = ln.decode("utf-8", "replace").strip()
                if "partial=" in ln:
                    marks.append("PARTIAL" if "partial=1" in ln else "FULL")
                elif "_Update_Full" in ln:
                    marks.append("Update_Full")
                elif "_Update_Part" in ln:
                    marks.append("Update_Part")
                elif "display 完成" in ln:
                    return marks
        return marks + ["TIMEOUT"]

    def pending(self):
        """缓冲区里是否已有一条未消费的 display（有 display 完成 无 开始 配对）"""
        return b"display \xe5\xae\x8c\xe6\x88\x90" in self.buf


def main():
    ser = Ser(PORT)
    ser.pump(3)

    r, responded = post("/api/scribe", json.dumps(
        {"title": "长文翻页", "text": LONG, "font": "small"},
        ensure_ascii=False))
    print("push ok=%s pages=%s responded=%s"
          % (r and r.get("ok"), r and r.get("pages"), responded))
    print("render0:", ser.wait_display())
    if responded:
        # sendOk 先回、渲染在后：再等一次才是本次渲染
        print("render0b:", ser.wait_display())

    for i in range(1, 7):
        step = "next" if i % 2 else "prev"
        r, responded = post("/api/mode", step, ct="text/plain;charset=utf-8")
        marks = ser.wait_display()
        if responded:
            marks2 = ser.wait_display()
            if marks2 and "TIMEOUT" not in marks2:
                marks = marks2
        print("step%d %-4s:" % (i, step), marks)
    ser.s.close()


if __name__ == "__main__":
    main()
