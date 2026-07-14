---
title: Cockpit Firmware Rendering
type: note
permalink: claudemon32/architecture/cockpit-firmware-rendering
created: 2026-07-12
updated: 2026-07-12
source_sha: eca43cc639b4e89a613b4281516a70f4720c015e
source_paths: esp32/crowpanel/src/UI.cpp, esp32/crowpanel/include/lv_conf.h, esp32/crowpanel/src/board_elecrow.cpp, esp32/crowpanel/platformio.ini
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: claude-opus-4-8
---

Durable firmware learnings from the Cockpit build (on the `cockpit-redesign` branch; supersedes the e-paper-era CrowPanel design). Source: esp32/crowpanel/src/UI.cpp, lv_conf.h, board_elecrow.cpp, platformio.ini.

## Observations
- [decision] The firmware renders ONLY the visible screen, freeing non-active screens and rebuilding them lazily on nav (`showScreen` in UI.cpp). Building all five fully-populated screens in one `ui_update` exhausted LVGL's object heap → null-deref crash in `lv_label_create` (the device ACKed the push, then rebooted to the boot screen — looked like a frozen/blank panel). Never build offscreen screens. #lvgl #crash-fix
- [constraint] LVGL's object pool is `LV_MEM_SIZE=96KB` in INTERNAL RAM (lv_conf.h), deliberately NOT PSRAM — PSRAM would contend with the panel's continuous framebuffer DMA and worsen jitter. One screen fits; five don't. #lvgl #psram
- [gotcha] RGB-panel jitter (a brief horizontal shift-right-then-back) is the LCD DMA starving the PSRAM framebuffer read. The lever is the pixel clock in board_elecrow.cpp: 21→16→**12 MHz** eliminated it (~30fps, still crisp). Lower pclk = more scan headroom; the higher-headroom alternative is 120MHz PSRAM. #rgb-panel #jitter
- [convention] The device ticks its own clock + 5h-reset countdown once/sec from the payload's `base` + per-account `fh_sec` — the ONE sanctioned relaxation of the host-rendering contract (it can't call the host between pushes). Everything else stays host-formatted. #live-tick
- [decision] Single ingestion seam: the `Dashboard` model is written ONLY by `Protocol::parseCockpit` and read ONLY by `ui_update()`, so a Phase-4 on-device fetcher can fill the same struct without touching the UI. #seam #phase-4
- [gotcha] The device font is built-in LVGL Montserrat (14/16/20/28) — ASCII + FontAwesome only. Host/firmware strings must be ASCII (see [[Device Font Glyph Limits]]). #fonts

## Relations
- part_of [[Cockpit Redesign Phase]]
- supersedes [[CrowPanel Extension]]
- relates_to [[CrowPanel Flashing and CH340 Boot-Mode Gotcha]]
- relates_to [[Host-Rendering Contract]]
