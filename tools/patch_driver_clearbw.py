# -*- coding: utf-8 -*-
"""
驱动补丁：移除 clear_full_bw()（v3 前置刷白方案，实机叠字，已弃用）。

根因（2026-10-29 实机复盘）：
  GDEY075Z08 是 UC8179 的 "Z08" 三色料号，RED buffer（0x13）不是第二块
  BW 帧 RAM。0x00=0x3f 寄存器 LUT 差分刷只把 0x13 的 0 当红驱动、
  1 当"不动作"——把旧内容写进 0x13 当差分基准，等于根本没有基准，
  每个差分周期都往屏面已有内容上再叠一层（用户所见：不停叠字）。
  官方 GxEPD2 驱动作者已在 lut_22 表头注释 "doesn't work on my panel"。
  唯一被驱动认可的屏面镜像是 0x10（black buffer）——v2 已实机验证稳定。

用法：python patch_driver_clearbw.py          （幂等，可重放）
还原：用 .orig 备份覆盖（若存在）或重刷官方驱动。
"""
import os
import re
import shutil
import sys

DRV_DIR = r"C:\Users\Administrator\Documents\Arduino\libraries\GxEPD2\src\gdey3c"
CPP = os.path.join(DRV_DIR, "GxEPD2_750c_GDEY075Z08.cpp")
H = os.path.join(DRV_DIR, "GxEPD2_750c_GDEY075Z08.h")
MARK = "epaper-panel local patch 2026-10-29"


def backup(path):
    orig = path + ".orig"
    if not os.path.exists(orig):
        shutil.copy2(path, orig)
        print(f"[备份] {orig}")


def remove_from_cpp():
    with open(CPP, "r", encoding="utf-8") as f:
        src = f.read()
    if "clear_full_bw" not in src:
        print("[跳过] .cpp 中已无 clear_full_bw")
        return
    backup(CPP)
    # 删除注释块 + 整个函数体（从补丁注释到函数结束大括号）
    pat = re.compile(
        r"// epaper-panel local patch 2026-10-29: heavy-duty white clear.*?"
        r"void GxEPD2_750c_GDEY075Z08::clear_full_bw\(\)\s*\{.*?\n\}\n\n",
        re.DOTALL,
    )
    new, n = pat.subn("", src)
    if n != 1:
        # 兜底：按行定位删除
        lines = src.splitlines(keepends=True)
        start = end = None
        depth = 0
        in_fn = False
        for i, ln in enumerate(lines):
            if MARK in ln and start is None:
                start = i
            if "void GxEPD2_750c_GDEY075Z08::clear_full_bw" in ln:
                in_fn = True
                if start is None:
                    start = i
            if in_fn:
                depth += ln.count("{") - ln.count("}")
                if depth == 0 and "}" in ln and i > start:
                    end = i + 1
                    # 连带尾随空行
                    while end < len(lines) and lines[end].strip() == "":
                        end += 1
                    break
        assert start is not None and end is not None, "定位 clear_full_bw 失败"
        new = "".join(lines[:start] + lines[end:])
        n = 1
    with open(CPP, "w", encoding="utf-8") as f:
        f.write(new)
    print(f"[完成] .cpp 已删除 clear_full_bw 实现（含补丁注释块）")


def remove_from_h():
    with open(H, "r", encoding="utf-8") as f:
        src = f.read()
    if "clear_full_bw" not in src:
        print("[跳过] .h 中已无 clear_full_bw")
        return
    backup(H)
    lines = [ln for ln in src.splitlines(keepends=True)
             if "clear_full_bw" not in ln]
    with open(H, "w", encoding="utf-8") as f:
        f.write("".join(lines))
    print("[完成] .h 已删除 clear_full_bw 声明")


if __name__ == "__main__":
    for p in (CPP, H):
        if not os.path.exists(p):
            sys.exit(f"[错误] 找不到 {p}")
    remove_from_cpp()
    remove_from_h()
    # 验证
    for p in (CPP, H):
        with open(p, encoding="utf-8") as f:
            assert "clear_full_bw" not in f.read(), f"{p} 仍有残留!"
    print("[验证] 驱动已恢复干净（clear_full_bw 完全移除）")
