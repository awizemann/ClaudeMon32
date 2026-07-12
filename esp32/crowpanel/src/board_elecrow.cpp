// Elecrow CrowPanel Advance 5.0" board bring-up — the ONE file that touches
// hardware. Implements the board_config.h seam for the rest of the firmware.
//
// Everything here is grafted from Elecrow's verified demo
// (lesson-03/BigInch_LVGL): the LovyanGFX LGFX device carries the exact RGB pin map
// + porch timings for this panel, and the GT911 touch controller is read through
// LovyanGFX's own Touch_GT911 (no separate touch lib). The non-obvious wrinkle is
// the backlight: on this V1.1 board it's owned by a companion MCU at I2C 0x30 (the
// V1.0 board used a TCA9534 at 0x18 instead — confirm with an I2C scan if a panel
// stays dark). Send it command 0x10 to turn the panel on. Pins/timings are copied
// verbatim from the demo; do not guess.

#include "board_config.h"
#include <lvgl.h>
#include <Wire.h>
#include <driver/i2c.h>

#define LGFX_USE_V1
#include <LovyanGFX.hpp>
#include <lgfx/v1/platforms/esp32s3/Panel_RGB.hpp>
#include <lgfx/v1/platforms/esp32s3/Bus_RGB.hpp>

// ---- LovyanGFX device: 800x480 RGB panel + GT911 touch (verified pin map) ----
class LGFX : public lgfx::LGFX_Device {
public:
    lgfx::Bus_RGB    _bus_instance;
    lgfx::Panel_RGB  _panel_instance;
    lgfx::Touch_GT911 _touch_instance;

    LGFX(void) {
        {
            auto cfg = _panel_instance.config();
            cfg.memory_width  = SCREEN_W;
            cfg.memory_height = SCREEN_H;
            cfg.panel_width   = SCREEN_W;
            cfg.panel_height  = SCREEN_H;
            cfg.offset_x = 0;
            cfg.offset_y = 0;
            _panel_instance.config(cfg);
        }
        {
            auto cfg = _panel_instance.config_detail();
            cfg.use_psram = 1;
            _panel_instance.config_detail(cfg);
        }
        {
            auto cfg = _bus_instance.config();
            cfg.panel = &_panel_instance;
            cfg.pin_d0  = GPIO_NUM_21;  // B0
            cfg.pin_d1  = GPIO_NUM_47;  // B1
            cfg.pin_d2  = GPIO_NUM_48;  // B2
            cfg.pin_d3  = GPIO_NUM_45;  // B3
            cfg.pin_d4  = GPIO_NUM_38;  // B4
            cfg.pin_d5  = GPIO_NUM_9;   // G0
            cfg.pin_d6  = GPIO_NUM_10;  // G1
            cfg.pin_d7  = GPIO_NUM_11;  // G2
            cfg.pin_d8  = GPIO_NUM_12;  // G3
            cfg.pin_d9  = GPIO_NUM_13;  // G4
            cfg.pin_d10 = GPIO_NUM_14;  // G5
            cfg.pin_d11 = GPIO_NUM_7;   // R0
            cfg.pin_d12 = GPIO_NUM_17;  // R1
            cfg.pin_d13 = GPIO_NUM_18;  // R2
            cfg.pin_d14 = GPIO_NUM_3;   // R3
            cfg.pin_d15 = GPIO_NUM_46;  // R4

            cfg.pin_henable = GPIO_NUM_42;
            cfg.pin_vsync   = GPIO_NUM_41;
            cfg.pin_hsync   = GPIO_NUM_40;
            cfg.pin_pclk    = GPIO_NUM_39;
            // 12 MHz pixel clock (down from the demo's 21 MHz, then 16 MHz). On the
            // stock 80 MHz PSRAM this Arduino core uses, the LCD DMA starves reading
            // the PSRAM framebuffer at higher clocks and the panel twitches — seen as
            // a brief horizontal shift-right-then-back, worse when the CPU also hits
            // PSRAM (e.g. the 1 Hz clock redraw). 12 MHz gives the scan more headroom
            // (~816x496 total / 12 MHz ≈ 30 fps, still flicker-free for static UI).
            // If it looks less crisp, nudge up; if it still twitches, try 10 MHz or
            // raise PSRAM to 120 MHz. See the jitter-tuning task.
            cfg.freq_write  = 12000000;

            cfg.hsync_polarity    = 0;
            cfg.hsync_front_porch = 8;
            cfg.hsync_pulse_width = 4;
            cfg.hsync_back_porch  = 8;
            cfg.vsync_polarity    = 0;
            cfg.vsync_front_porch = 8;
            cfg.vsync_pulse_width = 4;
            cfg.vsync_back_porch  = 8;
            cfg.pclk_idle_high    = 1;
            _bus_instance.config(cfg);
        }
        _panel_instance.setBus(&_bus_instance);

        {
            auto cfg = _touch_instance.config();
            cfg.x_min = 0;   cfg.x_max = SCREEN_W;
            cfg.y_min = 0;   cfg.y_max = SCREEN_H;
            cfg.pin_int = -1;               // INT unused; reset gated via TCA9534
            cfg.bus_shared = false;
            cfg.offset_rotation = 0;
            cfg.i2c_port = I2C_NUM_0;
            cfg.pin_sda = GPIO_NUM_15;
            cfg.pin_scl = GPIO_NUM_16;
            cfg.pin_rst = -1;
            cfg.freq = 400000;
            cfg.i2c_addr = 0x5D;            // GT911 (0x5D after the reset sequence)
            _touch_instance.config(cfg);
            _panel_instance.setTouch(&_touch_instance);
        }

        setPanel(&_panel_instance);
    }
};

static LGFX               s_gfx;
static lv_disp_draw_buf_t s_draw_buf;
static lv_color_t*        s_buf0 = nullptr;
static lv_color_t*        s_buf1 = nullptr;

// LVGL -> panel. Matches the demo: close any open write window, DMA the region,
// then report ready. Safe because we draw into two full-screen PSRAM buffers, so
// LVGL renders the next frame into the other buffer while this one DMAs out.
static void rgb_flush(lv_disp_drv_t* drv, const lv_area_t* area, lv_color_t* px) {
    if (s_gfx.getStartCount() > 0) s_gfx.endWrite();
    s_gfx.pushImageDMA(area->x1, area->y1,
                       area->x2 - area->x1 + 1,
                       area->y2 - area->y1 + 1,
                       (lgfx::rgb565_t*)&px->full);
    lv_disp_flush_ready(drv);
}

// GT911 capacitive touch read through LovyanGFX.
static void gt911_read(lv_indev_drv_t*, lv_indev_data_t* data) {
    uint16_t x = 0, y = 0;
    if (s_gfx.getTouch(&x, &y)) {
        data->state   = LV_INDEV_STATE_PR;
        data->point.x = x;
        data->point.y = y;
    } else {
        data->state = LV_INDEV_STATE_REL;
    }
}

// Companion power/backlight MCU on the V1.1 board lives at I2C 0x30 and takes
// one-byte commands. 0x19 nudges it awake; 0x10 turns the panel/backlight on.
static bool i2c_present(uint8_t addr) {
    Wire.beginTransmission(addr);
    return Wire.endTransmission() == 0;
}
static void mcu_cmd(uint8_t c) {
    Wire.beginTransmission(0x30);
    Wire.write(c);
    Wire.endTransmission();
}

// Bring the panel up: wait for the 0x30 power MCU and the GT911 (0x5D) to appear,
// nudging the MCU (and pulsing GPIO1, which resets the touch/panel MCU) until they
// do, then send 0x10 to enable the backlight. Verbatim from the V1.1 demo's setup().
static void power_on_panel() {
    pinMode(19, OUTPUT);          // kept as in the demo (harmless on the UART board)
    Wire.begin(15, 16);
    delay(50);

    for (int i = 0; i < 50; i++) {
        if (i2c_present(0x30) && i2c_present(0x5D)) break;
        mcu_cmd(0x19);            // nudge the power MCU awake
        pinMode(1, OUTPUT);
        digitalWrite(1, LOW);
        delay(120);
        pinMode(1, INPUT);
        delay(100);
    }

    mcu_cmd(0x10);               // turn the panel / backlight ON
}

void platform_lvgl_init() {
    power_on_panel();

    s_gfx.init();
    s_gfx.initDMA();
    s_gfx.startWrite();
    s_gfx.fillScreen(TFT_BLACK);

    lv_init();

    // Two full-screen buffers in PSRAM (768 KB each). A full 800x480 frame can't
    // live in internal RAM, and double buffering is what makes the DMA flush above
    // safe. 1.5 MB out of the 8 MB octal PSRAM.
    const size_t px = (size_t)SCREEN_W * SCREEN_H;
    s_buf0 = (lv_color_t*)heap_caps_malloc(px * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
    s_buf1 = (lv_color_t*)heap_caps_malloc(px * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
    lv_disp_draw_buf_init(&s_draw_buf, s_buf0, s_buf1, px);

    static lv_disp_drv_t disp_drv;
    lv_disp_drv_init(&disp_drv);
    disp_drv.hor_res  = SCREEN_W;
    disp_drv.ver_res  = SCREEN_H;
    disp_drv.flush_cb = rgb_flush;
    disp_drv.draw_buf = &s_draw_buf;
    lv_disp_drv_register(&disp_drv);

    static lv_indev_drv_t indev_drv;
    lv_indev_drv_init(&indev_drv);
    indev_drv.type    = LV_INDEV_TYPE_POINTER;
    indev_drv.read_cb = gt911_read;
    lv_indev_drv_register(&indev_drv);
}

void platform_lvgl_tick() {
    static uint32_t last = 0;
    uint32_t now = millis();
    lv_tick_inc(now - last);
    last = now;
    lv_timer_handler();
}
