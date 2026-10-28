# -*- coding: utf-8 -*-
"""临时抓串口：dsrdtr=False + 开端口后 dtr/rts=False（防止误复位），
抓 SECONDS 秒输出。用完即删。"""
import sys
import time
import serial

port = sys.argv[1] if len(sys.argv) > 1 else "COM6"
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 25

s = serial.Serial(port, 115200, timeout=0.5, dsrdtr=False)
s.dtr = False
s.rts = False
end = time.time() + seconds
buf = b""
while time.time() < end:
    chunk = s.read(4096)
    if chunk:
        buf += chunk
s.close()
text = buf.decode("utf-8", errors="replace")
print(text)
