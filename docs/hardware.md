# Hardware & Flashing

## The board

ClaudeMon targets the **SpotPear ESP32-S3 1.54-inch e-Paper** development board
(sold as "ESP32-S3-ePaper-1.54", also stocked by Waveshare resellers):

- ESP32-S3FH4R2 (8 MB flash, PSRAM), native USB-C
- 1.54" 200×200 mono e-paper, SSD1681 controller
- Onboard extras the firmware initializes but ClaudeMon doesn't need: SHTC3
  temp/humidity sensor, PCF85063 RTC, ES8311 audio codec, battery circuit
- **Product page:** [Waveshare ESP32-S3 e-Paper 1.54](https://www.waveshare.com/esp32-s3-epaper-1.54.htm) —
  this exact unit. Also stocked on SpotPear / AliExpress / Amazon
  (search "ESP32-S3 ePaper 1.54", ~$15–20)

Any other 200×200 SSD1681 ESP32-S3 board will likely work with pin changes in
`esp32/firmware/src/config.h`. Different panels/boards need a display-driver
port — the [serial protocol](protocol.md) is the stable interface.

## Flashing — prebuilt image (no toolchain)

Grab `claudemon-firmware-merged.bin` from the
[latest release](https://github.com/awizemann/ClaudeMon32/releases), install
esptool (`brew install esptool` or `uv tool install esptool`), plug the board
in, and:

```sh
esptool --chip esp32s3 --port /dev/cu.usbmodem* write_flash 0x0 claudemon-firmware-merged.bin
```

The merged image contains the bootloader, partition table, and app at their
correct offsets — one command, done. The device reboots into the ClaudeMon
boot screen ("WAITING FOR HOST").

If the port doesn't appear (`ls /dev/cu.usbmodem*` is empty), see
[troubleshooting](troubleshooting.md#device-not-showing-up-on-usb).

## Flashing — from source

```sh
brew install platformio          # or: uv tool install platformio
cd esp32/firmware
pio run -t upload --upload-port /dev/cu.usbmodem<YOURS>
pio device monitor               # 115200 baud; expect "[INIT] Ready."
```

`platformio.ini` pins the board config (`esp32-s3-devkitc-1`, 8 MB, OPI PSRAM,
USB-CDC on boot). Don't trust any `upload_port` committed there — ports are
per-machine; pass `--upload-port` explicitly.

## Backing up the factory firmware first (recommended)

The board ships with vendor demo firmware. If you want it back someday, dump
the flash before writing ClaudeMon (we don't redistribute the vendor image):

```sh
esptool --chip esp32s3 --port /dev/cu.usbmodem* read_flash 0x0 0x800000 factory_backup.bin
# restore later with:
esptool --chip esp32s3 --port /dev/cu.usbmodem* write_flash 0x0 factory_backup.bin
```

## Download mode

If flashing fails or the board stops enumerating: hold the **BOOT** button
while plugging in USB (or while pressing reset). That forces the ROM
bootloader, which always enumerates if power and data lines are good.
