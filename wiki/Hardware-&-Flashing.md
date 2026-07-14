# Hardware & Flashing

## The board

ClaudeMon targets the **SpotPear ESP32-S3 1.54" e-Paper** (also stocked by Waveshare resellers) [[memophant/architecture/hardware-targets]]:

- **ESP32-S3FH4R2**: 8 MB flash, PSRAM, native USB-C
- **1.54" e-paper**: 200×200 mono, SSD1681 controller
- Onboard extras (initialized by firmware but not used by ClaudeMon): SHTC3 temp/humidity sensor, PCF85063 RTC, ES8311 audio codec, battery circuit
- **Cost**: ~$15–20 (search "ESP32-S3 ePaper 1.54" on AliExpress, Amazon, SpotPear, Waveshare)
- **Product page**: [Waveshare ESP32-S3 e-Paper 1.54](https://www.waveshare.com/esp32-s3-epaper-1.54.htm)

Any other 200×200 SSD1681 ESP32-S3 board will likely work with pin changes in `esp32/firmware/src/config.h`. Different panels need firmware porting — the [Serial Protocol & Device Commands](Serial-Protocol-Device-Commands) is the stable interface.

## Flashing (prebuilt image, no toolchain required)

1. Grab `claudemon-firmware-merged.bin` from the [latest release](https://github.com/awizemann/ClaudeMon32/releases)
2. Install esptool: `brew install esptool` or `uv tool install esptool`
3. Plug the board into USB (use a **data cable**, not charge-only)
4. Find the port: `ls /dev/cu.usbmodem*`
5. Flash:
   ```sh
   esptool --chip esp32s3 --port /dev/cu.usbmodem* write_flash 0x0 claudemon-firmware-merged.bin
   ```

The merged image contains bootloader, partition table, and app at the correct offsets — one command, done. On success, the device reboots into the ClaudeMon boot screen ("WAITING FOR HOST").

### No port enumerated?

In rough order of likelihood:

1. **Charge-only cable** — The #1 failure. Use a known data cable (USB-C, with data lines).
2. **Board is powered off** — This board has a PWR button (GPIO18) — short-press it. If the e-paper shows nothing, the board isn't running.
3. **Force download mode** — Hold the **BOOT** button while plugging in. If it *still* doesn't enumerate, the cable/port/board is at fault (the ESP32-S3 ROM bootloader always enumerates when power and data lines are good).

Different boards enumerate with different port names: native-USB S3 boards appear as `usbmodem*`; boards with a CP210x/CH340 bridge appear as `usbserial*` / `SLAB*` / `wchusbserial*`. ClaudeMon scans all of these.

## Backing up the factory firmware

Before flashing, you can dump the original firmware (we don't redistribute it):

```sh
esptool --chip esp32s3 --port /dev/cu.usbmodem* read_flash 0x0 0x800000 factory_backup.bin
# Restore later:
esptool --chip esp32s3 --port /dev/cu.usbmodem* write_flash 0x0 factory_backup.bin
```

## Building from source

```sh
brew install platformio       # or: uv tool install platformio
cd esp32/firmware
pio run -t upload --upload-port /dev/cu.usbmodem<YOURS>
pio device monitor            # 115200 baud; watch for "[INIT] Ready."
```

`platformio.ini` pins the board config (esp32-s3-devkitc-1, 8 MB, OPI PSRAM, USB-CDC). Don't trust any committed `upload_port` — ports are per-machine; pass `--upload-port` explicitly.

## Troubleshooting flashing

**"Port is busy" when flashing?** The background agent holds the serial port. Stop it first:

```sh
claudeemon uninstall-agent
pio run -t upload --upload-port /dev/cu.usbmodem<YOURS>
claudeemon install-agent
```