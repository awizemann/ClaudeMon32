---
title: Hardware Targets
type: note
permalink: claudemon32/architecture/hardware-targets
created: 2026-07-12
updated: 2026-07-12
tags:
- hardware
- esp32
- e-paper
- crowpanel
source_sha: d86396092a9b0330d39c97e50feec71105e83f10
source_paths: docs/hardware.md, docs/protocol.md
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: audit:claude-haiku-4-5
---

## Observations
- [primary] **SpotPear / Waveshare ESP32-S3 1.54" e-Paper** (esp32/firmware): ESP32-S3FH4R2 (8 MB flash, PSRAM), native USB-C, 200×200 mono SSD1681 panel. Also carries shtc3 temp/humidity, PCF85063 RTC, ES8311 codec, battery circuit (firmware initializes but doesn't use). Pin config in `esp32/firmware/src/config.h`; porting to another 200×200 SSD1681 board is a config change. #esp32-s3 #e-paper #waveshare
- [secondary] **Elecrow CrowPanel Advance 5.0"** (esp32/crowpanel, added later): also ESP32-S3, but 800×480 IPS color display with **LVGL** firmware. Richer dashboard payload (set_dashboard); owns rendering instead of host-rendering-only like e-paper. #crowpanel #lvgl #color-display
- [flashing] Prebuilt images from Releases: `esptool --chip esp32s3 --port /dev/cu.usbmodem* write_flash 0x0 claudemon-firmware-merged.bin` (merged image contains bootloader, partition table, app). Or from source: `pio run -t upload --upload-port /dev/cu.usbmodem<PORT>`. #esptool #platformio

## Relations
- constrains [[Serial Protocol]]
- constrains [[E-paper Display Integration]]
