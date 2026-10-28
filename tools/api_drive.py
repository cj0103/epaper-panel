# -*- coding: utf-8 -*-
"""API 投喂 + 串口日志同窗采集（验证刷新策略用）。

用法：
    python api_drive.py [端口] [抓取秒数]
流程：后台线程持续抓串口 → 依次推送 scribe/模式切换/整刷 → 打印抓到的关键行。
"""
import json
import sys
import threading
import time
import urllib.request

import serial

BASE = "http://192.168.31.62"
PORT = sys.argv[1] if len(sys.argv) > 1 else "COM6"
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 60

lines = []


def post(path, body, ct="text/plain;charset=utf-8", timeout=10):
    req = urllib.request.Request(BASE + path, data=body.encode("utf-8"),
                                 headers={"Content-Type": ct}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:                       # noqa: BLE001
        return {"_err": str(e)}


def wait_free(deadline=90.0):
    """轮询 /api/status 直到设备空闲（一次整刷要 19~27 秒，期间设备不服务）。
    连接被重置（ConnectionResetError）= 设备正忙于刷屏，继续等。"""
    t0 = time.time()
    ok = False
    while time.time() - t0 < deadline:
        try:
            with urllib.request.urlopen(BASE + "/api/status", timeout=30) as r:
                json.loads(r.read().decode("utf-8"))
            if ok:
                return True          # 之前忙过、现在空了
            ok = True                # 先记录一次"空闲"，再取一次确认
        except Exception:            # noqa: BLE001
            ok = False
        time.sleep(0.5)
    return not ok                    # 一直没忙 = 本来空闲


def wait_after_post(settle=2.0):
    """post 返回后等渲染真正启动（loop 50ms 轮询），再等它刷完。"""
    time.sleep(settle)
    return wait_free()


def main():
    s = serial.Serial(PORT, 115200, timeout=0.5, dsrdtr=False)
    s.dtr = False
    s.rts = False
    stop = threading.Event()

    def reader():
        buf = b""
        while not stop.is_set():
            chunk = s.read(2048)
            if chunk:
                buf += chunk
        lines.extend(buf.decode("utf-8", "replace").splitlines())
        s.close()

    th = threading.Thread(target=reader, daemon=True)
    th.start()

    body = "春天来了，院子里的桃花都开了。"
    # 1) 推一段誊抄（渲染1）
    print("scribe:", post("/api/scribe",
                          json.dumps({"title": "刷新链路测试", "text": body,
                                      "font": "small"}, ensure_ascii=False),
                          "application/json"), wait_after_post())
    # 2) 模式切换（渲染2~4：连续快刷，第4次应被计数器强制转整刷）
    print("mode scribe:", post("/api/mode", "scribe"), wait_after_post())
    print("mode timetable:", post("/api/mode", "timetable"), wait_after_post())
    print("mode scribe:", post("/api/mode", "scribe"), wait_after_post())
    print("mode notice(无公告应报错):", post("/api/mode", "notice"))
    # 3) 手动整刷（渲染5：应走 _Update_Full）
    print("refresh:", post("/api/mode", "refresh", timeout=40), wait_after_post())

    stop.set()
    th.join(timeout=3)
    for ln in lines:
        if any(k in ln for k in ("display(partial", "_Update", "display 完成",
                                 "渲染]", "[API]")):
            print("LOG:", ln)


if __name__ == "__main__":
    main()
