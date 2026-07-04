#include "EPD154.h"

static const uint8_t WF_Full[159] = {
    0x80,0x48,0x40,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x40,0x48,0x80,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x80,0x48,0x40,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x40,0x48,0x80,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0xA,0x0,0x0,0x0,0x0,0x0,0x0,
    0x8,0x1,0x0,0x8,0x1,0x0,0x2,
    0xA,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x22,0x22,0x22,0x22,0x22,0x22,0x0,0x0,0x0,
    0x22,0x17,0x41,0x0,0x32,0x20
};

static const uint8_t WF_Partial[159] = {
    0x0,0x40,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x80,0x80,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x40,0x40,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x80,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0xF,0x0,0x0,0x0,0x0,0x0,0x0,
    0x1,0x1,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x0,0x0,0x0,0x0,0x0,0x0,0x0,
    0x22,0x22,0x22,0x22,0x22,0x22,0x0,0x0,0x0,
    0x02,0x17,0x41,0xB0,0x32,0x28,
};

EPD154::EPD154()
{
    memset(_buffer, 0xFF, BUF_LEN);
}

// Bitbanged SPI Mode 0: CPOL=0 (idle LOW), CPHA=0 (sample on rising edge)
void EPD154::spiSend(uint8_t byte) {
    for (int bit = 7; bit >= 0; bit--) {
        // Set data while clock is LOW
        gpio_set_level((gpio_num_t)EPD_MOSI, (byte >> bit) & 1);
        esp_rom_delay_us(1);
        // Rising edge — data sampled by SSD1681
        gpio_set_level((gpio_num_t)EPD_SCK, 1);
        esp_rom_delay_us(1);
        // Falling edge — return clock to idle LOW
        gpio_set_level((gpio_num_t)EPD_SCK, 0);
    }
}

void EPD154::spiSendBuf(const uint8_t* buf, int len) {
    for (int i = 0; i < len; i++) spiSend(buf[i]);
}

void EPD154::sendCommand(uint8_t cmd) {
    gpio_set_level((gpio_num_t)EPD_DC, 0);
    gpio_set_level((gpio_num_t)EPD_CS, 0);
    spiSend(cmd);
    gpio_set_level((gpio_num_t)EPD_CS, 1);
}

void EPD154::sendData(uint8_t data) {
    gpio_set_level((gpio_num_t)EPD_DC, 1);
    gpio_set_level((gpio_num_t)EPD_CS, 0);
    spiSend(data);
    gpio_set_level((gpio_num_t)EPD_CS, 1);
}

void EPD154::sendDataBuf(const uint8_t* buf, int len) {
    gpio_set_level((gpio_num_t)EPD_DC, 1);
    gpio_set_level((gpio_num_t)EPD_CS, 0);
    spiSendBuf(buf, len);
    gpio_set_level((gpio_num_t)EPD_CS, 1);
}

void EPD154::waitBusy() {
    uint32_t start = millis();
    while (gpio_get_level((gpio_num_t)EPD_BUSY) == 1) {
        vTaskDelay(pdMS_TO_TICKS(5));
        if (millis() - start > 10000) {
            Serial.println("[EPD] BUSY timeout!");
            return;
        }
    }
}

void EPD154::hwReset() {
    gpio_set_level((gpio_num_t)EPD_RST, 1);
    vTaskDelay(pdMS_TO_TICKS(50));
    gpio_set_level((gpio_num_t)EPD_RST, 0);
    vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level((gpio_num_t)EPD_RST, 1);
    vTaskDelay(pdMS_TO_TICKS(50));
}

void EPD154::setWindows(uint16_t xs, uint16_t ys, uint16_t xe, uint16_t ye) {
    sendCommand(0x44);
    sendData((xs >> 3) & 0xFF);
    sendData((xe >> 3) & 0xFF);
    sendCommand(0x45);
    sendData(ys & 0xFF); sendData((ys >> 8) & 0xFF);
    sendData(ye & 0xFF); sendData((ye >> 8) & 0xFF);
}

void EPD154::setCursor(uint16_t x, uint16_t y) {
    sendCommand(0x4E); sendData(x & 0xFF);
    sendCommand(0x4F); sendData(y & 0xFF); sendData((y >> 8) & 0xFF);
}

void EPD154::setLut(const uint8_t* lut) {
    sendCommand(0x32);
    sendDataBuf(lut, 153);
    waitBusy();
    sendCommand(0x3F); sendData(lut[153]);
    sendCommand(0x03); sendData(lut[154]);
    sendCommand(0x04); sendData(lut[155]); sendData(lut[156]); sendData(lut[157]);
    sendCommand(0x2C); sendData(lut[158]);
}

void EPD154::turnOnDisplay() {
    sendCommand(0x22); sendData(0xC7);
    sendCommand(0x20);
    waitBusy();
}

void EPD154::turnOnDisplayPart() {
    sendCommand(0x22); sendData(0xCF);
    sendCommand(0x20);
    waitBusy();
}

void EPD154::init() {
    Serial.println("[EPD] Init (bitbang SPI)...");

    // Power on — sequence from official firmware:
    // 1. VBAT power (GPIO 17) HIGH
    // 2. EPD power (GPIO 6) LOW (active low!)
    // 3. Audio power (GPIO 42) LOW (active low!)
    gpio_config_t pwr = {};
    pwr.pin_bit_mask = (1ULL << VBAT_PWR) | (1ULL << EPD_PWR) | (1ULL << AUDIO_PWR);
    pwr.mode = GPIO_MODE_OUTPUT;
    pwr.pull_up_en = GPIO_PULLUP_ENABLE;
    gpio_config(&pwr);

    gpio_set_level((gpio_num_t)VBAT_PWR, 1);   // VBAT: active HIGH
    gpio_set_level((gpio_num_t)EPD_PWR, 0);     // EPD: active LOW
    gpio_set_level((gpio_num_t)AUDIO_PWR, 0);   // Audio: active LOW
    delay(200);

    // GPIO config — output: CS, DC, RST, MOSI, SCK; input: BUSY
    gpio_config_t out = {};
    out.intr_type = GPIO_INTR_DISABLE;
    out.mode = GPIO_MODE_OUTPUT;
    out.pin_bit_mask = (1ULL<<EPD_RST)|(1ULL<<EPD_DC)|(1ULL<<EPD_CS)
                     |(1ULL<<EPD_MOSI)|(1ULL<<EPD_SCK);
    out.pull_up_en = GPIO_PULLUP_ENABLE;
    gpio_config(&out);

    gpio_config_t in = {};
    in.mode = GPIO_MODE_INPUT;
    in.pin_bit_mask = (1ULL << EPD_BUSY);
    gpio_config(&in);

    gpio_set_level((gpio_num_t)EPD_CS, 1);
    gpio_set_level((gpio_num_t)EPD_SCK, 0);  // SPI Mode 0: SCK idles LOW

    // Init sequence (from official Waveshare driver)
    hwReset();
    waitBusy();

    sendCommand(0x12);  // SW reset
    waitBusy();

    sendCommand(0x01);  // Driver output control
    sendData(0xC7); sendData(0x00); sendData(0x01);

    sendCommand(0x11);  // Data entry mode
    sendData(0x01);

    setWindows(0, WIDTH - 1, HEIGHT - 1, 0);

    sendCommand(0x3C);  // Border waveform
    sendData(0x01);

    sendCommand(0x18);  // Temperature sensor
    sendData(0x80);

    sendCommand(0x22);  // Load temp + waveform
    sendData(0xB1);
    sendCommand(0x20);

    setCursor(0, HEIGHT - 1);
    waitBusy();

    setLut(WF_Full);

    Serial.println("[EPD] Init complete");
}

void EPD154::clear() {
    memset(_buffer, 0xFF, BUF_LEN);
}

void EPD154::setPixel(uint16_t x, uint16_t y, bool black) {
    if (x >= WIDTH || y >= HEIGHT) return;
    uint16_t index = y * 25 + (x >> 3);
    uint8_t bit = 7 - (x & 0x07);
    if (black) _buffer[index] &= ~(1 << bit);
    else       _buffer[index] |= (1 << bit);
}

void EPD154::display() {
    // Write to BOTH RAM planes (0x24 = new, 0x26 = old/base).
    // The SSD1681 LUT uses the comparison between planes to drive
    // the waveform. Writing both ensures a clean full refresh
    // regardless of what was previously in the display RAM.
    sendCommand(0x24);
    sendDataBuf(_buffer, BUF_LEN);
    sendCommand(0x26);
    sendDataBuf(_buffer, BUF_LEN);
    turnOnDisplay();
}

void EPD154::initPartial() {
    hwReset();
    waitBusy();
    setLut(WF_Partial);

    sendCommand(0x37);
    sendData(0x00); sendData(0x00); sendData(0x00); sendData(0x00);
    sendData(0x00); sendData(0x40); sendData(0x00); sendData(0x00);
    sendData(0x00); sendData(0x00);

    sendCommand(0x3C); sendData(0x80);
    sendCommand(0x22); sendData(0xC0);
    sendCommand(0x20);
    waitBusy();
}

void EPD154::displayPartial() {
    sendCommand(0x24);
    sendDataBuf(_buffer, BUF_LEN);
    turnOnDisplayPart();
}
