#ifndef EPD154_H
#define EPD154_H

#include <Arduino.h>
#include <driver/gpio.h>
#include "../config.h"

// SSD1681 driver for Spotpear 1.54" 200x200 e-paper.
// Uses bitbanged SPI — the ESP-IDF SPI peripheral doesn't work
// reliably with this board's display, but bitbanging does.

class EPD154 {
public:
    EPD154();

    void init();
    void clear();
    void setPixel(uint16_t x, uint16_t y, bool black);
    void display();        // Full refresh
    void displayPartial(); // Partial refresh (after initPartial)
    void initPartial();

    uint8_t* getBuffer() { return _buffer; }
    static constexpr int WIDTH  = 200;
    static constexpr int HEIGHT = 200;
    static constexpr int BUF_LEN = WIDTH * HEIGHT / 8;

private:
    void spiSend(uint8_t byte);
    void spiSendBuf(const uint8_t* buf, int len);
    void sendCommand(uint8_t cmd);
    void sendData(uint8_t data);
    void sendDataBuf(const uint8_t* buf, int len);
    void waitBusy();
    void hwReset();
    void setWindows(uint16_t xs, uint16_t ys, uint16_t xe, uint16_t ye);
    void setCursor(uint16_t x, uint16_t y);
    void setLut(const uint8_t* lut);
    void turnOnDisplay();
    void turnOnDisplayPart();

    uint8_t _buffer[BUF_LEN];
};

#endif
