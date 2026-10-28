# -*- coding: utf-8 -*-
"""硬复位 ESP32 并抓串口日志（不烧录，只复位+抓取）。

ESP32 经典复位脉冲：DTR/RTS 组合 -> EN(GPIO_EN) 拉低复位。
复位后立即恢复 DTR/RTS=False，避免把芯片按在下载模式。

用法：
    python reset_pulse.py [端口] [秒数]
"""
import sys
import time

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "COM6"
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 40

s = serial.Serial(port, 115200, timeout=0.5, dsrdtr=False)
# 复位脉冲：RTS=EN 低有效
s.dtr = False
s.rts = True
time.sleep(0.12)
s.rts = False
time.sleep(0.05)
# 关键：立即松手，否则可能被按进下载模式
s.dtr = False
s.rts = False

end = time.time() + seconds
buf = b""
while time.time() < end:
    chunk = s.read(4096)
    if chunk:
        buf += chunk
s.close()
print(buf.decode("utf-8", errors="replace"))
