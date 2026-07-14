---
title: CrowPanel Flashing and CH340 Boot-Mode Gotcha
type: note
permalink: claudemon32/operations/crowpanel-flashing-and-ch340-boot-mode-gotcha
created: 2026-07-12
updated: 2026-07-12
source_sha: 76d691655c3633607966e5d1bb6564d0f868e5c1
source_paths: esp32/crowpanel/platformio.ini
source_paths_inferred: true
---

## Observations
- [gotcha] The CrowPanel (CH340 UART0) can get stuck in ESP32-S3 **DOWNLOAD mode** — boot log `rst:0x1 (POWERON),boot:0x0 (DOWNLOAD(USB/UART0)) / waiting for download`. In this state the app isn't running: the device is **totally silent** on serial, `claudemon dashboard --push` fails with `no JSON response to ping within 3.0s`, and the screen sits blank / on the last frame. Confirmed 2026-07-12 during Cockpit Phase-2 bring-up. #serial #boot-mode
- [gotcha] Cause: GPIO0 (IO0) is driven via the CH340 DTR/RTS auto-reset transistors, and this board's macOS CH34x driver is **flaky about the DTR/RTS reset ioctls** (per `esp32/crowpanel/platformio.ini`, which sets `--before no_reset --after hard_reset` + manual button flashing). Opening the port with the wrong DTR/RTS can latch the chip into download mode at the next reset edge. Software reset from pyserial is unreliable (sometimes toggles, usually silent). #ch340 #dtr-rts
- [fix] **Recovery = flash it.** When stuck in download mode the board is already waiting for download, so `cd esp32/crowpanel && pio run -t upload --upload-port /dev/cu.wchusbserial<N>` connects and flashes cleanly; esptool's post-flash `Hard resetting via RTS pin` then boots the app, and `claudemon dashboard --push` works immediately after. #recovery
- [ops] To flash when the app IS running (not in download): physically enter download first — **hold BOOT, tap RST, release BOOT** — then run the upload. Auto-enter-bootloader does not work (that's why platformio.ini uses no_reset). Port is `/dev/cu.wchusbserial20130` on Alan's machine; pin it with `--port`. #flashing
- [ops] The `claudemon run` launchd daemon (`com.claudemon.agent`) holds the serial port and pushes `set_usage` (e-paper payload) which the CrowPanel rejects — stop it (`launchctl bootout gui/$(id -u)/com.claudemon.agent`) before manual `dashboard --push`. Making the daemon push `set_cockpit` is a Cockpit Phase-3 task. #daemon #port-contention

## Relations
- relates_to [[Serial Protocol]]
- relates_to [[Cockpit Redesign Phase]]
- relates_to [[Hardware Targets]]
