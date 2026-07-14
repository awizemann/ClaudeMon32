---
title: CrowPanel Header Widget Layout
type: note
permalink: claudemon32/conventions/crowpanel-header-widget-layout
created: 2026-07-13
updated: 2026-07-13
source_sha: 89d36c76657ae54b7288a1d072bd5fa76ec5fbf5
source_paths: esp32/crowpanel/src/UI.cpp
source_paths_inferred: false
---

Hard-won during the WiFi-icon work: the home header's `right` cluster is a nested SIZE_CONTENT flex, and it silently eats SIZE_CONTENT children. This trap cost real time three separate times (clock clipped, status pill invisible, WiFi icon absent) before the pattern was clear.

## Observations
- [gotcha] In the CrowPanel home header's nested SIZE_CONTENT flex (the `right` cluster in buildHeaders), SIZE_CONTENT flex children collapse to zero width and don't render — this hid the status pill and the first WiFi-icon attempts, and clipped the clock. #firmware #lvgl #flex
- [convention] Header widgets must be fixed-size (like the clock's 96x46 clockcol) or a FLOATING absolutely-aligned overlay (LV_OBJ_FLAG_FLOATING + lv_obj_align) — never a SIZE_CONTENT child inside the header flex row. The WiFi icon is floating, pinned left of the clock. #firmware #lvgl
- [gotcha] LV_SYMBOL_* glyphs (e.g. LV_SYMBOL_WIFI) render blank — our Montserrat fonts are built WITHOUT the FontAwesome symbol range. Draw icons from lv_obj rectangles instead (the WiFi 'signal bars' are three rects). #firmware #lvgl #fonts
- [convention] A FLOATING overlay toggles cleanly with the HIDDEN flag (no relayout); ui_set_wifi does this from the 1 Hz tick keyed on net_wifi_up(). #firmware #lvgl

## Relations
- relates_to [[Cockpit Firmware Rendering]]
- relates_to [[Device Font Glyph Limits]]
