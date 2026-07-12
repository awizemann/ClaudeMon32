// Board bring-up seam for the Elecrow CrowPanel Advance 5.0".
//
// Everything board-SPECIFIC (the ST7262 RGB panel timings, the GT911 touch pins,
// and wiring LVGL's display/input drivers to them) lives behind this interface
// so the rest of the firmware — Protocol, Dashboard, UI — stays hardware-neutral.
//
// The panel + touch setup in board_elecrow.cpp is grafted from Elecrow's verified
// CrowPanel Advance 5.0 demo (example_code5.0/lesson-03/BigInch_LVGL): a LovyanGFX
// LGFX device (Panel_RGB + Bus_RGB + Touch_GT911) plus a TCA9534 I2C expander that
// gates the backlight and the GT911 reset. Pins/timings are copied verbatim from
// that demo — not hand-guessed. Source repo:
//   github.com/Elecrow-RD/CrowPanel-Advance-5-HMI-ESP32-S3-AI-Powered-IPS-Touch-Screen-800x480
#pragma once

#include <Arduino.h>

static const uint16_t SCREEN_W = 800;
static const uint16_t SCREEN_H = 480;

// Bring up the panel + touch and register both LVGL drivers. Must call lv_init()
// and allocate the draw buffer in PSRAM (heap_caps_malloc(..., MALLOC_CAP_SPIRAM))
// — an 800x480x16bpp full buffer is 768 KB, far past internal RAM. A 1/10th
// partial buffer (~48 KB) is the usual compromise; both must be PSRAM-backed.
void platform_lvgl_init();

// Feed LVGL its millisecond tick + run its timer handler. Call every loop().
void platform_lvgl_tick();
