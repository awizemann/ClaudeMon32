#ifndef DISPLAY_MANAGER_H
#define DISPLAY_MANAGER_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <vector>
#include <map>
#include "EPD154.h"

struct WidgetDef {
    String type;
    int16_t x, y, w, h;
    String label;
    String dataBinding;
    uint8_t fontSize;
    String valueFormat;    // "currency", "percent", "number", "temperature", ""
    int16_t cornerRadius;  // 0 = sharp corners, 4-6 = rounded
};

struct LayoutDef {
    String name;
    std::vector<WidgetDef> widgets;
};

class DisplayManager {
public:
    DisplayManager();

    void init();
    void clear();

    // --- Text (5x7 font) ---
    void drawText(int16_t x, int16_t y, const char* text, uint8_t scale);
    void drawCenteredText(int16_t y, const char* text, uint8_t scale);
    int  textWidth(const char* text, uint8_t scale);

    // --- Large number font (16px) ---
    void drawCharLarge(int16_t x, int16_t y, char c, bool invert = false);
    void drawTextLarge(int16_t x, int16_t y, const char* text, bool invert = false);
    int  textWidthLarge(const char* text);
    void drawCenteredTextLarge(int16_t y, int16_t cx, const char* text);

    // --- Shape primitives ---
    void drawLine(int16_t x1, int16_t y1, int16_t x2, int16_t y2);
    void drawRect(int16_t x, int16_t y, int16_t w, int16_t h);
    void fillRect(int16_t x, int16_t y, int16_t w, int16_t h, bool black);
    void drawRoundRect(int16_t x, int16_t y, int16_t w, int16_t h, int16_t r);
    void fillRoundRect(int16_t x, int16_t y, int16_t w, int16_t h, int16_t r, bool black);

    // --- Bitmap ---
    void drawBitmap(int16_t x, int16_t y, const uint8_t* bitmap,
                    int16_t bw, int16_t bh, bool color);

    // --- Refresh ---
    void fullRefresh();
    void partialRefresh();

    // --- Widgets ---
    void renderTextWidget(int16_t x, int16_t y, int16_t w, int16_t h,
                          const char* label, const char* value,
                          int16_t cornerRadius = 0);
    void renderStatusBar(bool wifiConnected, bool bleConnected, uint8_t batteryPercent = 0);

    // --- Layout system ---
    void setLayout(const LayoutDef& layout);
    void renderLayout(const std::map<String, String>& dataValues,
                      bool wifiConnected = false, bool bleConnected = false,
                      uint8_t batteryPercent = 0);
    bool parseLayoutJson(const String& json, LayoutDef& layout);
    String serializeLayout(const LayoutDef& layout);
    bool hasLayout() const;

    // Public for diagnostic access
    EPD154 _epd;

private:
    void renderWidget(const WidgetDef& widget, const String& value);
    void drawChar(int16_t x, int16_t y, char c, uint8_t scale);
    void drawCircleQuadrant(int16_t cx, int16_t cy, int16_t r,
                            uint8_t corners, bool black);
    void fillCircleHelper(int16_t cx, int16_t cy, int16_t r,
                          uint8_t sides, int16_t delta, bool black);
    bool canUseLargeFont(const char* text);

    LayoutDef _currentLayout;
    bool _hasLayout;
};

#endif // DISPLAY_MANAGER_H
