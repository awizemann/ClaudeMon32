# Third-Party Licenses & Attribution

ClaudeMon itself is [MIT](../LICENSE). The firmware links or derives from:

| Component | License | Role |
|---|---|---|
| [ArduinoJson](https://github.com/bblanchon/ArduinoJson) | MIT | JSON protocol parsing |
| [NimBLE-Arduino](https://github.com/h2zero/NimBLE-Arduino) | Apache-2.0 | BLE transport |
| [arduino-esp32](https://github.com/espressif/arduino-esp32) (Arduino core + ESP-IDF) | LGPL-2.1 (core) / Apache-2.0 (IDF) | Framework |
| SSD1681 waveform lookup tables in `esp32/firmware/src/display/EPD154.cpp` | MIT-style (vendor demo) | Panel refresh waveforms |
| 5×7 bitmap font in `DisplayManager.cpp` | classic public-domain glyph set | Text rendering |

Notes:

- **Waveform LUTs** (`WF_Full` / `WF_Partial`): panel-specific byte tables of the
  kind distributed in the display vendor's reference demos (Waveshare/SpotPear
  e-paper examples carry an MIT-style "Permission is hereby granted…" header).
  The rest of the EPD154 driver is original to this project.
- **LGPL-2.1 (arduino-esp32 core)** and the prebuilt firmware images on the
  Releases page: the complete corresponding source and build configuration for
  those binaries is this repository (`esp32/firmware/`, PlatformIO). Anyone can
  modify the library or application and rebuild an equivalent image with
  `pio run`, which satisfies the relink/rebuild requirement.
- The host tool's Python dependencies (`httpx`, `pyserial`) are BSD-3-Clause
  licensed and are installed, not vendored.
