---
title: pioarduino Platform Migration and WiFi Crash Fix
type: note
permalink: claudemon32/decisions/pioarduino-platform-migration-and-wifi-crash-fix
created: 2026-07-14
updated: 2026-07-14
source_sha: 0c215bf59a31769c04bacfdf9c64349084c624f5
source_paths: esp32/crowpanel/platformio.ini, esp32/crowpanel/src/Net.cpp
source_paths_inferred: false
---

The CrowPanel firmware rebooted every ~15-30 min once WiFi was enabled — a WiFi-stack heap-corruption panic, fixed by migrating the build platform. Root-caused live (serial backtrace + heap instrumentation + prebuilt-sdkconfig inspection), then fixed on branch pioarduino-migration (commit 0c215bf), off cockpit-redesign. Not merged, not pushed.

## Observations
- [decision] The crowpanel firmware builds on pioarduino (platform release 55.03.39 = arduino-esp32 3.3.9 / ESP-IDF 5.5), migrated from the archived `platform = espressif32` (arduino 2.0.17 / IDF 4.4). #pioarduino #platform
- [gotcha] Root cause of the WiFi reboot: the precompiled arduino 2.0.17 qio_opi libs ship CONFIG_ESP32S3_DATA_CACHE_LINE_SIZE=32 (wrong for octal-PSRAM 64-byte bursts) AND CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP=1 (WiFi buffers in PSRAM); small cached CPU writes corrupt them -> multi_heap_free poison assert in esf_buf_recycle/ppTask. Framebuffer survives (aligned DMA), so it only crashed with WiFi. #crash #psram
- [decision] Fix = pioarduino custom_sdkconfig (hybrid from-source recompile): CONFIG_ESP32S3_DATA_CACHE_LINE_64B=y + CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP=n (WiFi buffers now in internal SRAM). These are baked into the precompiled libs, so a source-recompiling platform is required. #fix #sdkconfig
- [gotcha] pioarduino hybrid build compiles ALL of arduino-esp32's bundled managed components; strip unused ones (modbus/zigbee/esp-sr/ethernet PHYs...) via custom_component_remove and CONFIG_BT_ENABLED=n, or their config asserts fail the build. Also: never `-I src` (the from-source IDF picks up our src/Net.h over ble_mesh's net.h on the case-insensitive macOS FS) — lv_conf.h lives in include/ with `-I include`. #build #gotcha
- [fact] Migration cost only one code change (WiFiServer.available()->accept()) + LovyanGFX ^1.1.16->^1.2.0 and lvgl ^8.3->^8.4. Verified: display + real-time clock + touch + WiFi + mDNS all work; soaked ~1.5h with zero reboots (was 15-30 min). #verified

## Relations
- relates_to [[Cockpit WiFi Transport]]
- relates_to [[Cockpit Firmware Rendering]]
- relates_to [[Hardware Targets]]
