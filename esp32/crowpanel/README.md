# ClaudeMon — CrowPanel firmware (5" target)

Firmware for the **Elecrow CrowPanel Advance 5.0"** (ESP32-S3-WROOM-1-N16R8,
800×480 IPS, ST7262 RGB panel, GT911 capacitive touch, CH340 USB-UART). It
renders a dense analytics dashboard — Claude usage + Cloudflare + GitHub — from
the host's `set_dashboard` payload ([../../docs/protocol.md](../../docs/protocol.md)).

This is a **separate target** from `esp32/firmware` (the 1.54" e-paper board).
They share the serial protocol; they share no display code.

## Design

The host still owns everything that matters — OAuth, tokens, fetching, and all
string formatting. The device owns **only layout**, because 800×480 color can't
be pushed as pixels over serial (~768 KB/frame). So unlike the e-paper firmware
("draw exactly these strings"), this one renders with LVGL. Data model in
`Dashboard.h`, parse in `Protocol.cpp`, layout in `UI.cpp`, hardware in
`board_elecrow.cpp`.

```
serial line ─▶ Protocol::handle ─▶ Dashboard model ─▶ ui_update() ─▶ LVGL ─▶ RGB panel
```

## Status: working on hardware

Board bring-up is **complete and running on the device**. `board_elecrow.cpp`
drives the real 800×480 RGB panel (LovyanGFX) and GT911 capacitive touch, with
the V1.1 companion-MCU (I²C `0x30`) backlight power-on sequence — verified pins
and porch timings copied from Elecrow's demo. The serial framing, the
`set_dashboard` parser, the data model, and the LVGL dashboard all run live.

Current UI is a 4-page **tab-bar/swipe** dashboard (Claude / Cloudflare / GitHub
/ System). This is being **superseded** by the *ClaudeMon Cockpit* redesign
(`design/design_handoff_claudemon_cockpit/`): a home grid → drill-in source
pages, an alerts panel, a new Paddle source, and a web admin. See the roadmap
note `cockpit-redesign-phase` for the phased plan and the Mac-brain-vs-autonomy
decision (building Mac-brain first, seams cut for later on-device autonomy).

> Editor red squiggles (`'Arduino.h' file not found`, unknown `lv_*` types) are
> just the host clang lacking the ESP32/LVGL toolchain — they vanish under the
> PlatformIO build. The e-paper firmware shows the same.

## Rebuild + flash

The CrowPanel needs the **WCH CH34x** driver on macOS; it then enumerates as
`/dev/cu.wchusbserial*`.

```sh
cd esp32/crowpanel
pio run -t upload --upload-port /dev/cu.wchusbserial<YOURS>
pio device monitor    # expect "[INIT] Ready."
```

Drive it from the host:

```sh
claudemon set-token cloudflare      # then add-zone / set-token github / add-repo
claudemon dashboard --push          # fetch all sources and push set_dashboard
```
