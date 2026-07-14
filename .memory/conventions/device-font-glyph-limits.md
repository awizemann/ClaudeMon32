---
title: Device Font Glyph Limits
type: note
permalink: claudemon32/conventions/device-font-glyph-limits
created: 2026-07-12
updated: 2026-07-12
---

## Observations
- [convention] The CrowPanel LVGL UI uses the built-in Montserrat bitmap fonts at **14/16/20/28** only. These cover ASCII + the FontAwesome `LV_SYMBOL_*` set, but **not** common typographic glyphs: `·` (U+00B7 middot), `×` (U+00D7 mult sign), `‹`/`›` (U+2039/203A), `★` (U+2605), `•` (U+2022). Any of these render as a tofu box / stray artifact on the panel. #firmware #fonts
- [convention] So **every string reaching the device — host-rendered strings AND firmware literals — must use ASCII substitutes**: `-` for `·`, `x` for `×`, `<`/`>` for `‹`/`›`, `*` for `★`. This bit us twice during Cockpit Phase 2 (`·` separators and `×` in "Max 20x" plan chips). The design mockups use the fancy glyphs; the firmware approximates with ASCII. #host-rendering #gotcha
- [todo] When wiring **real** Anthropic plan/messages/etc. (currently unwired — usage.py doesn't parse plan yet), format plan as `"Max 20x"` (ASCII), not `"Max 20×"`. Same for any new host-formatted field. #phase-3
- [idea] To get pixel-perfect design glyphs (`·`, `×`, real back chevrons, stars), build a **custom LVGL font** with the extra codepoints via `lv_font_conv` — costs flash, so only if the aesthetics matter enough. #font-gen

## Relations
- refines [[Host-Rendering Contract]]
- relates_to [[Cockpit Redesign Phase]]
