# -*- coding: utf-8 -*-
"""
给 GxEPD2 驱动 GxEPD2_750c_GDEY075Z08 注入 clear_full_bw()：
整屏"加重刷白"（寄存器 LUT，K->W 相位 5->12 帧 / W->W 5->8 帧），
用于每次 BW 差分快刷前重置残影电荷态。

幂等：已注入则跳过。首次运行自动备份 .orig。
"""
import shutil, os, sys

D = r"C:\Users\Administrator\Documents\Arduino\libraries\GxEPD2\src\gdey3c"
CPP = os.path.join(D, "GxEPD2_750c_GDEY075Z08.cpp")
H = os.path.join(D, "GxEPD2_750c_GDEY075Z08.h")

IMPL = """
// epaper-panel local patch 2026-10-29: heavy-duty white clear before BW
// content refresh, to reset ghosting charge state each fast-refresh cycle.
// Same register-LUT mechanism as refresh_bw, but the drive phases toward
// white are strengthened (K->W 5->12 frames, W->W 5->8 frames) so the
// white pass fully re-drives pixels regardless of previous state.
void GxEPD2_750c_GDEY075Z08::clear_full_bw()
{
  if (!_init_display_done) _InitDisplay();
  _writeCommand(0x00); // PANEL SETTING
  _writeData(0x1f);    // (placeholder, switched to register LUT right below)
  _writeCommand(0x00); // panel setting
  _writeData(0x3f);    // partial update LUT from registers
  _writeCommand(0x82); // vcom_DC setting
  _writeData (0x30);   // -2.5V same value as in OTP
  _writeCommand(0x50); // VCOM AND DATA INTERVAL SETTING
  _writeData(0xA0);    // floating border
  _writeData(0x07);
  _writeCommand(0x20); // LUTC
  _writeDataPGM(lut_20_LUTC_partial, sizeof(lut_20_LUTC_partial), 42 - sizeof(lut_20_LUTC_partial));
  _writeCommand(0x21); // LUTWW
  _writeDataPGM(lut_21_LUTWW_partial, sizeof(lut_21_LUTWW_partial), 42 - sizeof(lut_21_LUTWW_partial));
  _writeCommand(0x22); // LUTKW
  {
    static const uint8_t lut_kw_strong[] PROGMEM = {
      0x20, 0x3,  0x5, 0x0, 0x0,  2,
      0x20, 0x5,  0x5, 0x0, 0x0,  1,
      0x0,  0xC,  0xC, 0x0, 0x0,  1,
      0x20, 0xC,  0xC, 0x0, 0x0,  3,
      0x0,  0x0,  0x0, 0x0, 0x0,  0,
      0x0,  0x0,  0x0, 0x0, 0x0,  0,
      0x0,  0x0,  0x0, 0x0, 0x0,  0,
    };
    _writeDataPGM(lut_kw_strong, sizeof(lut_kw_strong), 42 - sizeof(lut_kw_strong));
  }
  _writeCommand(0x23); // LUTWK
  {
    static const uint8_t lut_wk_strong[] PROGMEM = {
      0x40, 0x3,  0x5, 0x0, 0x0,  2,
      0x40, 0x5,  0x5, 0x0, 0x0,  1,
      0x0,  0x8,  0x8, 0x0, 0x0,  1,
      0x40, 0x8,  0x8, 0x0, 0x0,  3,
      0x0,  0x0,  0x0, 0x0, 0x0,  0,
      0x0,  0x0,  0x0, 0x0, 0x0,  0,
      0x0,  0x0,  0x0, 0x0, 0x0,  0,
    };
    _writeDataPGM(lut_wk_strong, sizeof(lut_wk_strong), 42 - sizeof(lut_wk_strong));
  }
  _writeCommand(0x24); // LUTKK
  _writeDataPGM(lut_24_LUTKK_partial, sizeof(lut_24_LUTKK_partial), 42 - sizeof(lut_24_LUTKK_partial));
  _writeCommand(0x25); // LUTBD
  _writeDataPGM(lut_25_LUTBD_partial, sizeof(lut_25_LUTBD_partial), 42 - sizeof(lut_25_LUTBD_partial));
  // white target: new-frame RAM (0x10) and old-frame RAM (0x13) both 0xFF
  _writeScreenBuffer(0x10, 0xFF);
  _writeScreenBuffer(0x13, 0xFF);
  _PowerOn();
  _writeCommand(0x12); // display refresh
  _waitWhileBusy("clear_full_bw", full_refresh_time);
}

"""

HEADER_DECL = "    void clear_full_bw(); // epaper-panel patch: full-screen white clear (heavy register LUT), resets ghosting before BW content refresh\n"


def main():
    for f in (CPP, H):
        if not os.path.exists(f + ".orig"):
            shutil.copy2(f, f + ".orig")
            print("backup:", f + ".orig")

    raw = open(CPP, "rb").read()
    if b"clear_full_bw" in raw:
        print("cpp: already patched")
    else:
        # 注意：必须插在 refresh_bw 函数定义【之前】。曾把新函数体插到
        # "函数头+\n{" 之后 = 嵌进旧函数体内，编译报 qualified-id 错误。
        anchor = "void GxEPD2_750c_GDEY075Z08::refresh_bw(int16_t x, int16_t y, int16_t w, int16_t h)".encode()
        assert raw.count(anchor) == 1, raw.count(anchor)
        open(CPP, "wb").write(raw.replace(anchor, IMPL.lstrip("\n").encode() + "\n" + anchor, 1))
        print("cpp: patched")

    hr = open(H, "rb").read()
    if b"clear_full_bw" in hr:
        print("h: already patched")
    else:
        a2 = "    void refresh_bw(int16_t x, int16_t y, int16_t w, int16_t h); // screen refresh from controller memory, partial screen, bw differential\n".encode()
        assert hr.count(a2) == 1, hr.count(a2)
        open(H, "wb").write(hr.replace(a2, a2 + HEADER_DECL.encode(), 1))
        print("h: patched")


if __name__ == "__main__":
    sys.exit(main())
