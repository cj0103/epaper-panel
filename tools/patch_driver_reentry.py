# -*- coding: utf-8 -*-
"""
驱动补丁（2026-10-30 根因修复）：0x13 写入通道的 partial 窗口防残留。

实机叠字根因（代码审查定案，GDEY075Z08 / UC8179）：
  UC8179 的 partial-in（0x91）是"粘的"：置位后，后续所有 RAM 写入
  （0x10/0x13）都被裁进最近一次 0x90 partial window，直到 0x92 清除。
  官方驱动 GxEPD2_750c_GDEY075Z08 的 0x13（previous/红侧）写入路径
  存在残留窗口风险：
    - _writeScreenBuffer()（:51）进入时 0x91/0x92 双双注释——若任何
      时序留下未闭合的 partial-in（如 v3 的 clear_full_bw：两次
      _writeScreenBuffer 裸写 + 0x12 刷新，全程无 0x92），0x13 的
      "全屏"写实际被裁进上一刷的 0x90 窗口；
    - 差分链 writeImageToPrevious 之后 0x13 通道是否完整覆盖整屏
      无法从软件侧确认。
  RAM 与软件镜像一旦失步，差分每刷都在旧内容上叠新内容；整刷写
  RAM 同样可能被裁，救不回基准——表现为"翻页、切誊抄怎么刷都叠字"
  （2026-10-29 晚～10-30 用户实机）。

修复（保守版，只加防御、不改驱动原有动作）：
  1) _writeScreenBuffer 进入时先 0x92 partial out——清掉任何上游
     残留，保证全屏刷白/刷黑真正全屏（非 partial 态收到 0x92 无副作用）；
  2) writeImageToPrevious 写完 0x13 后补一次显式全屏窗口回写
     （0x91 + 0x90全屏 + 0x13 全帧 + 0x92）——自包含、自闭合，
     无论之前窗口/粘滞状态如何，都能把"previous 侧 RAM = 上一帧"
     这一差分基准强制立正。

用法：python patch_driver_reentry.py     （幂等，自动 .orig 备份）
还原：copy .orig 回原名（.orig 是本补丁首次运行前的文件快照）。
"""
import os
import shutil
import sys

DRV = r"C:\Users\Administrator\Documents\Arduino\libraries\GxEPD2\src\gdey3c"
CPP = os.path.join(DRV, "GxEPD2_750c_GDEY075Z08.cpp")
H = os.path.join(DRV, "GxEPD2_750c_GDEY075Z08.h")
MARK = "epaper-panel patch 2026-10-30"

# ---- 1) _writeScreenBuffer 进入防残留 ----
WSB_OLD = (
    "void GxEPD2_750c_GDEY075Z08::_writeScreenBuffer(uint8_t command, uint8_t value)\n"
    "{\n"
)
WSB_NEW = (
    "void GxEPD2_750c_GDEY075Z08::_writeScreenBuffer(uint8_t command, uint8_t value)\n"
    "{\n"
    f"  _writeCommand(0x92); // {MARK}: clear stale partial-in before full-screen write\n"
)

# ---- 2) writeImageToPrevious 强制全屏回写 ----
WIP_OLD = (
    "void GxEPD2_750c_GDEY075Z08::writeImageToPrevious(const uint8_t bitmap[], int16_t x, int16_t y,"
    " int16_t w, int16_t h, bool invert, bool mirror_y, bool pgm)\n"
    "{\n"
    "  _writeImage(0x13, bitmap, x, y, w, h, invert, mirror_y, pgm);\n"
    "}\n"
)
WIP_NEW = (
    "void GxEPD2_750c_GDEY075Z08::writeImageToPrevious(const uint8_t bitmap[], int16_t x, int16_t y,"
    " int16_t w, int16_t h, bool invert, bool mirror_y, bool pgm)\n"
    "{\n"
    "  _writeImage(0x13, bitmap, x, y, w, h, invert, mirror_y, pgm);\n"
    f"  // {MARK}: force a full-screen, self-contained re-write of the previous-side\n"
    "  // RAM (0x13). If a sticky partial-in had clipped the write above to a stale\n"
    "  // 0x90 window, differential refresh would stack new content on old. The call\n"
    "  // below pairs its own 0x91/0x92 with a full-screen 0x90 window, so the result\n"
    "  // is identical whenever the first write was already complete (idempotent).\n"
    "  _writeImage(0x13, bitmap, 0, 0, WIDTH, HEIGHT, invert, mirror_y, pgm);\n"
    "}\n"
)


def patch_file(path, jobs):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if MARK in src:
        print(f"[跳过] {os.path.basename(path)} 已打过补丁")
        return
    for old, new in jobs:
        assert src.count(old) == 1, f"{os.path.basename(path)} 锚点不唯一/未找到:\n{old[:90]}..."
        src = src.replace(old, new)
    orig = path + ".orig"
    if not os.path.exists(orig):
        shutil.copy2(path, orig)
        print(f"[备份] {orig}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[完成] {os.path.basename(path)} 已打 {len(jobs)} 处补丁")


def main():
    for p in (CPP, H):
        if not os.path.exists(p):
            sys.exit(f"[错误] 找不到 {p}")
    patch_file(CPP, [(WSB_OLD, WSB_NEW), (WIP_OLD, WIP_NEW)])
    # 头文件无需改动（未新增成员/函数），此处仅一致性校验
    with open(CPP, encoding="utf-8") as f:
        src = f.read()
    assert src.count(MARK) >= 2, "补丁打点缺失"
    print("[验证] 驱动补丁就位")


if __name__ == "__main__":
    main()
