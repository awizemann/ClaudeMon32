---
title: Dependency Licenses
type: note
permalink: claudemon32/decisions/dependency-licenses
created: 2026-07-12
updated: 2026-07-12
tags:
- licenses
- lgpl
- compliance
- third-party
source_sha: d86396092a9b0330d39c97e50feec71105e83f10
source_paths: docs/licenses.md, LICENSE
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: audit:claude-haiku-4-5
---

## Observations
- [decision] ClaudeMon itself is MIT. Firmware links ArduinoJson (MIT), NimBLE-Arduino (Apache-2.0), arduino-esp32 core + ESP-IDF (LGPL-2.1 / Apache-2.0), SSD1681 waveform LUTs (MIT-style from vendor demo), 5×7 bitmap font (public-domain classic glyph set). #lgpl #third-party
- [compliance] LGPL-2.1 (arduino-esp32 core) compliance: the complete corresponding source and build config for prebuilt firmware images *is this repository* (`esp32/firmware/`, PlatformIO). Anyone can modify and rebuild an equivalent image with `pio run`, satisfying the relink/rebuild requirement. #lgpl-compliance #source-availability
- [notes] SSD1681 waveform tables (`WF_Full`/`WF_Partial` in EPD154.cpp): panel-specific byte tables from vendor reference demos (carry MIT-style 'Permission is hereby granted' header). Rest of EPD154 driver is original to this project. #waveform-tables

## Relations
- constrains [[Hardware Targets]]
