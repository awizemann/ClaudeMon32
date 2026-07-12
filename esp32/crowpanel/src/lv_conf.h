// Minimal LVGL v8 config (activated by -DLV_CONF_INCLUDE_SIMPLE in platformio.ini).
// lv_conf_internal.h fills defaults for every macro not set here, so this only
// overrides what the CrowPanel dashboard needs. Phase 0 may replace this wholesale
// with the tuned lv_conf.h from Elecrow's demo — keep whichever builds cleanly.
#ifndef LV_CONF_H
#define LV_CONF_H

#include <stdint.h>

#define LV_COLOR_DEPTH 16          // RGB565, matches the ST7262 panel
#define LV_COLOR_16_SWAP 0         // set to 1 if colors render byte-swapped

// LVGL's own heap. Draw buffers are allocated separately in PSRAM by the board
// layer; this pool is just for widget objects/styles.
#define LV_MEM_SIZE (64U * 1024U)

#define LV_TICK_CUSTOM 0           // we feed ticks via lv_tick_inc() in board layer
#define LV_DPI_DEF 130

// Fonts used by the dense dashboard.
#define LV_FONT_MONTSERRAT_14 1
#define LV_FONT_MONTSERRAT_16 1
#define LV_FONT_MONTSERRAT_20 1
#define LV_FONT_MONTSERRAT_28 1
#define LV_FONT_DEFAULT &lv_font_montserrat_16

// Widgets the dashboard uses (bars for percents, labels for everything else,
// tileview for the swipeable command-center pages).
#define LV_USE_BAR      1
#define LV_USE_LABEL    1
#define LV_USE_TILEVIEW 1
#define LV_USE_CHART    1     // sparklines on the Cloudflare page

#endif // LV_CONF_H
