#ifndef CONFIG_H
#define CONFIG_H

// ============================================================
// Spotpear/Waveshare ESP32-S3 1.54" e-Paper AIoT Board
// Pin definitions — V1 layout (confirmed working by original firmware)
// ============================================================

// --- E-ink SPI (SSD1681, 200x200 BW) ---
#define EPD_MOSI  13
#define EPD_SCK   12
#define EPD_CS    11
#define EPD_DC    10
#define EPD_RST    9
#define EPD_BUSY   8
#define EPD_PWR    6   // EPD1V3_EN — ACTIVE LOW! (0=ON, 1=OFF)

// --- I2C (shared bus: ES8311, SHTC3, PCF85063) ---
#define I2C_SDA   47
#define I2C_SCL   48

// --- I2S (ES8311 audio codec) ---
#define I2S_MCLK  14
#define I2S_BCLK  15
#define I2S_LRCK  38
#define I2S_DIN   16
#define I2S_DOUT  45

// --- Power control ---
// EPD_PWR and AUDIO_PWR are ACTIVE LOW (0=ON, 1=OFF)
// VBAT_PWR is ACTIVE HIGH (1=ON, 0=OFF)
#define SPEAKER_EN  46  // PA enable for speaker amplifier
#define AUDIO_PWR   42  // Audio codec power — ACTIVE LOW
#define VBAT_PWR    17  // Battery power rail — ACTIVE HIGH

// --- Battery ADC ---
#define BAT_ADC      4  // Battery voltage via resistor divider (2:1)

// --- Buttons ---
#define BOOT_BUTTON  0
#define PWR_BUTTON  18

// ============================================================
// Device Configuration
// ============================================================

#define DEVICE_NAME    "ESP32-S3 ePaper"
#define FIRMWARE_VER   "0.3.0"

// ============================================================
// BLE
// ============================================================

#define BLE_NUS_SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define BLE_NUS_RX_UUID      "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define BLE_NUS_TX_UUID      "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

// ============================================================
// Display
// ============================================================

#define DISPLAY_WIDTH  200
#define DISPLAY_HEIGHT 200

#define I2C_SHTC3_ADDR    0x70
#define I2C_PCF85063_ADDR 0x51

#endif // CONFIG_H
