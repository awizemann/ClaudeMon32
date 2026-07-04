#include "DisplayManager.h"
#include "Icons.h"
#include "FontLarge.h"
#include "ValueFormatter.h"
#include "../config.h"

// Basic 5x7 font for text rendering
static const uint8_t font5x7[][5] PROGMEM = {
    {0x00,0x00,0x00,0x00,0x00}, // space
    {0x00,0x00,0x5F,0x00,0x00}, // !
    {0x00,0x07,0x00,0x07,0x00}, // "
    {0x14,0x7F,0x14,0x7F,0x14}, // #
    {0x24,0x2A,0x7F,0x2A,0x12}, // $
    {0x23,0x13,0x08,0x64,0x62}, // %
    {0x36,0x49,0x55,0x22,0x50}, // &
    {0x00,0x05,0x03,0x00,0x00}, // '
    {0x00,0x1C,0x22,0x41,0x00}, // (
    {0x00,0x41,0x22,0x1C,0x00}, // )
    {0x08,0x2A,0x1C,0x2A,0x08}, // *
    {0x08,0x08,0x3E,0x08,0x08}, // +
    {0x00,0x50,0x30,0x00,0x00}, // ,
    {0x08,0x08,0x08,0x08,0x08}, // -
    {0x00,0x60,0x60,0x00,0x00}, // .
    {0x20,0x10,0x08,0x04,0x02}, // /
    {0x3E,0x51,0x49,0x45,0x3E}, // 0
    {0x00,0x42,0x7F,0x40,0x00}, // 1
    {0x42,0x61,0x51,0x49,0x46}, // 2
    {0x21,0x41,0x45,0x4B,0x31}, // 3
    {0x18,0x14,0x12,0x7F,0x10}, // 4
    {0x27,0x45,0x45,0x45,0x39}, // 5
    {0x3C,0x4A,0x49,0x49,0x30}, // 6
    {0x01,0x71,0x09,0x05,0x03}, // 7
    {0x36,0x49,0x49,0x49,0x36}, // 8
    {0x06,0x49,0x49,0x29,0x1E}, // 9
    {0x00,0x36,0x36,0x00,0x00}, // :
    {0x00,0x56,0x36,0x00,0x00}, // ;
    {0x00,0x08,0x14,0x22,0x41}, // <
    {0x14,0x14,0x14,0x14,0x14}, // =
    {0x41,0x22,0x14,0x08,0x00}, // >
    {0x02,0x01,0x51,0x09,0x06}, // ?
    {0x32,0x49,0x79,0x41,0x3E}, // @
    {0x7E,0x11,0x11,0x11,0x7E}, // A
    {0x7F,0x49,0x49,0x49,0x36}, // B
    {0x3E,0x41,0x41,0x41,0x22}, // C
    {0x7F,0x41,0x41,0x22,0x1C}, // D
    {0x7F,0x49,0x49,0x49,0x41}, // E
    {0x7F,0x09,0x09,0x01,0x01}, // F
    {0x3E,0x41,0x41,0x51,0x32}, // G
    {0x7F,0x08,0x08,0x08,0x7F}, // H
    {0x00,0x41,0x7F,0x41,0x00}, // I
    {0x20,0x40,0x41,0x3F,0x01}, // J
    {0x7F,0x08,0x14,0x22,0x41}, // K
    {0x7F,0x40,0x40,0x40,0x40}, // L
    {0x7F,0x02,0x04,0x02,0x7F}, // M
    {0x7F,0x04,0x08,0x10,0x7F}, // N
    {0x3E,0x41,0x41,0x41,0x3E}, // O
    {0x7F,0x09,0x09,0x09,0x06}, // P
    {0x3E,0x41,0x51,0x21,0x5E}, // Q
    {0x7F,0x09,0x19,0x29,0x46}, // R
    {0x46,0x49,0x49,0x49,0x31}, // S
    {0x01,0x01,0x7F,0x01,0x01}, // T
    {0x3F,0x40,0x40,0x40,0x3F}, // U
    {0x1F,0x20,0x40,0x20,0x1F}, // V
    {0x7F,0x20,0x18,0x20,0x7F}, // W
    {0x63,0x14,0x08,0x14,0x63}, // X
    {0x03,0x04,0x78,0x04,0x03}, // Y
    {0x61,0x51,0x49,0x45,0x43}, // Z
};

// =====================================================================
// Constructor & Init
// =====================================================================

DisplayManager::DisplayManager()
    : _hasLayout(false)
{
}

void DisplayManager::init()
{
    _epd.init();
    Serial.println("[Display] EPD154 driver initialized");
}

void DisplayManager::clear()
{
    _epd.clear();
}

// =====================================================================
// 5x7 Font Rendering
// =====================================================================

void DisplayManager::drawChar(int16_t x, int16_t y, char c, uint8_t scale)
{
    if (c >= 'a' && c <= 'z') c = c - 'a' + 'A';
    if (c < ' ' || c > 'Z') return;
    int idx = c - ' ';
    if (idx < 0 || idx >= 59) return;

    for (int col = 0; col < 5; col++) {
        uint8_t line = pgm_read_byte(&font5x7[idx][col]);
        for (int row = 0; row < 7; row++) {
            if (line & (1 << row)) {
                for (uint8_t sx = 0; sx < scale; sx++)
                    for (uint8_t sy = 0; sy < scale; sy++)
                        _epd.setPixel(x + col * scale + sx, y + row * scale + sy, true);
            }
        }
    }
}

int DisplayManager::textWidth(const char* text, uint8_t scale)
{
    return strlen(text) * 6 * scale;
}

void DisplayManager::drawText(int16_t x, int16_t y, const char* text, uint8_t scale)
{
    while (*text) {
        drawChar(x, y, *text, scale);
        x += 6 * scale;
        text++;
    }
}

void DisplayManager::drawCenteredText(int16_t y, const char* text, uint8_t scale)
{
    int w = textWidth(text, scale);
    drawText((DISPLAY_WIDTH - w) / 2, y, text, scale);
}

// =====================================================================
// Large Number Font (16px)
// =====================================================================

bool DisplayManager::canUseLargeFont(const char* text)
{
    while (*text) {
        if (largeFontIndex(*text) < 0) return false;
        text++;
    }
    return true;
}

void DisplayManager::drawCharLarge(int16_t x, int16_t y, char c, bool invert)
{
    int8_t idx = largeFontIndex(c);
    if (idx < 0) return;

    uint8_t w = pgm_read_byte(&largeFontWidths[idx]);
    if (idx == 0) return;  // Space — just advance, no bitmap

    const uint8_t* glyph = (const uint8_t*)pgm_read_ptr(&largeFontGlyphs[idx]);
    if (glyph == nullptr) return;

    uint8_t bytesPerRow = (w + 7) / 8;

    for (int16_t row = 0; row < LARGE_FONT_HEIGHT; row++) {
        for (int16_t col = 0; col < w; col++) {
            uint8_t byteIdx = row * bytesPerRow + (col / 8);
            uint8_t bit = 7 - (col % 8);
            bool set = pgm_read_byte(&glyph[byteIdx]) & (1 << bit);
            if (set) {
                _epd.setPixel(x + col, y + row, !invert);
            }
        }
    }
}

void DisplayManager::drawTextLarge(int16_t x, int16_t y, const char* text, bool invert)
{
    while (*text) {
        int8_t idx = largeFontIndex(*text);
        if (idx >= 0) {
            drawCharLarge(x, y, *text, invert);
            uint8_t w = pgm_read_byte(&largeFontWidths[idx]);
            x += w + 2;  // 2px spacing between chars
        }
        text++;
    }
}

int DisplayManager::textWidthLarge(const char* text)
{
    int total = 0;
    bool first = true;
    while (*text) {
        int8_t idx = largeFontIndex(*text);
        if (idx >= 0) {
            if (!first) total += 2;  // Spacing
            total += pgm_read_byte(&largeFontWidths[idx]);
            first = false;
        }
        text++;
    }
    return total;
}

void DisplayManager::drawCenteredTextLarge(int16_t y, int16_t cx, const char* text)
{
    int w = textWidthLarge(text);
    drawTextLarge(cx - w / 2, y, text);
}

// =====================================================================
// Shape Primitives
// =====================================================================

void DisplayManager::drawLine(int16_t x1, int16_t y1, int16_t x2, int16_t y2)
{
    if (y1 == y2) {
        for (int x = min(x1, x2); x <= max(x1, x2); x++)
            _epd.setPixel(x, y1, true);
    } else if (x1 == x2) {
        for (int y = min(y1, y2); y <= max(y1, y2); y++)
            _epd.setPixel(x1, y, true);
    }
}

void DisplayManager::drawRect(int16_t x, int16_t y, int16_t w, int16_t h)
{
    drawLine(x, y, x + w - 1, y);
    drawLine(x, y + h - 1, x + w - 1, y + h - 1);
    drawLine(x, y, x, y + h - 1);
    drawLine(x + w - 1, y, x + w - 1, y + h - 1);
}

void DisplayManager::fillRect(int16_t x, int16_t y, int16_t w, int16_t h, bool black)
{
    for (int16_t dy = 0; dy < h; dy++)
        for (int16_t dx = 0; dx < w; dx++)
            _epd.setPixel(x + dx, y + dy, black);
}

// Bresenham circle quadrant drawing for rounded rect corners
// corners bitmask: 1=top-right, 2=bottom-right, 4=bottom-left, 8=top-left
void DisplayManager::drawCircleQuadrant(int16_t cx, int16_t cy, int16_t r,
                                         uint8_t corners, bool black)
{
    int16_t f = 1 - r;
    int16_t ddF_x = 1;
    int16_t ddF_y = -2 * r;
    int16_t x = 0;
    int16_t y = r;

    while (x <= y) {
        if (corners & 1) { _epd.setPixel(cx + y, cy - x, black); _epd.setPixel(cx + x, cy - y, black); }
        if (corners & 2) { _epd.setPixel(cx + y, cy + x, black); _epd.setPixel(cx + x, cy + y, black); }
        if (corners & 4) { _epd.setPixel(cx - x, cy + y, black); _epd.setPixel(cx - y, cy + x, black); }
        if (corners & 8) { _epd.setPixel(cx - y, cy - x, black); _epd.setPixel(cx - x, cy - y, black); }

        if (f >= 0) {
            y--;
            ddF_y += 2;
            f += ddF_y;
        }
        x++;
        ddF_x += 2;
        f += ddF_x;
    }
}

// Fill helper for rounded rect corners using scanlines
// sides: 1=right half, 2=left half
void DisplayManager::fillCircleHelper(int16_t cx, int16_t cy, int16_t r,
                                       uint8_t sides, int16_t delta, bool black)
{
    int16_t f = 1 - r;
    int16_t ddF_x = 1;
    int16_t ddF_y = -2 * r;
    int16_t x = 0;
    int16_t y = r;

    while (x <= y) {
        if (sides & 1) {
            // Right side: fill scanlines from center to right
            for (int16_t i = cx; i <= cx + y; i++) {
                _epd.setPixel(i, cy + x + delta, black);
                _epd.setPixel(i, cy - x, black);
            }
            for (int16_t i = cx; i <= cx + x; i++) {
                _epd.setPixel(i, cy + y + delta, black);
                _epd.setPixel(i, cy - y, black);
            }
        }
        if (sides & 2) {
            // Left side
            for (int16_t i = cx - y; i <= cx; i++) {
                _epd.setPixel(i, cy + x + delta, black);
                _epd.setPixel(i, cy - x, black);
            }
            for (int16_t i = cx - x; i <= cx; i++) {
                _epd.setPixel(i, cy + y + delta, black);
                _epd.setPixel(i, cy - y, black);
            }
        }

        if (f >= 0) {
            y--;
            ddF_y += 2;
            f += ddF_y;
        }
        x++;
        ddF_x += 2;
        f += ddF_x;
    }
}

void DisplayManager::drawRoundRect(int16_t x, int16_t y, int16_t w, int16_t h, int16_t r)
{
    if (r <= 0) { drawRect(x, y, w, h); return; }
    if (r > h / 2) r = h / 2;
    if (r > w / 2) r = w / 2;

    // Horizontal edges (between corners)
    drawLine(x + r, y, x + w - r - 1, y);             // Top
    drawLine(x + r, y + h - 1, x + w - r - 1, y + h - 1);  // Bottom
    // Vertical edges (between corners)
    drawLine(x, y + r, x, y + h - r - 1);             // Left
    drawLine(x + w - 1, y + r, x + w - 1, y + h - r - 1);  // Right

    // Corner arcs
    drawCircleQuadrant(x + w - r - 1, y + r, r, 1, true);       // Top-right
    drawCircleQuadrant(x + w - r - 1, y + h - r - 1, r, 2, true); // Bottom-right
    drawCircleQuadrant(x + r, y + h - r - 1, r, 4, true);       // Bottom-left
    drawCircleQuadrant(x + r, y + r, r, 8, true);               // Top-left
}

void DisplayManager::fillRoundRect(int16_t x, int16_t y, int16_t w, int16_t h,
                                    int16_t r, bool black)
{
    if (r <= 0) { fillRect(x, y, w, h, black); return; }
    if (r > h / 2) r = h / 2;
    if (r > w / 2) r = w / 2;

    // Central rectangle
    fillRect(x + r, y, w - 2 * r, h, black);
    // Side fills via circle helpers
    fillCircleHelper(x + w - r - 1, y + r, r, 1, h - 2 * r - 1, black);
    fillCircleHelper(x + r, y + r, r, 2, h - 2 * r - 1, black);
}

// =====================================================================
// Bitmap
// =====================================================================

void DisplayManager::drawBitmap(int16_t x, int16_t y, const uint8_t* bitmap,
                                 int16_t bw, int16_t bh, bool color)
{
    int16_t bytesPerRow = (bw + 7) / 8;
    for (int16_t row = 0; row < bh; row++) {
        for (int16_t col = 0; col < bw; col++) {
            uint8_t byteIdx = row * bytesPerRow + (col / 8);
            uint8_t bit = 7 - (col % 8);
            if (pgm_read_byte(&bitmap[byteIdx]) & (1 << bit)) {
                _epd.setPixel(x + col, y + row, color);
            }
        }
    }
}

// =====================================================================
// Refresh
// =====================================================================

void DisplayManager::fullRefresh()
{
    _epd.display();
}

void DisplayManager::partialRefresh()
{
    _epd.initPartial();
    _epd.displayPartial();
}

// =====================================================================
// Status Bar (icons)
// =====================================================================

void DisplayManager::renderStatusBar(bool wifiConnected, bool bleConnected, uint8_t batteryPercent)
{
    fillRect(0, 0, DISPLAY_WIDTH, 14, true);  // Black bar

    // --- Left side: WiFi + BLE icons grouped ---
    const uint8_t* wifiIcon = wifiConnected ? icon_wifi_on : icon_wifi_off;
    drawBitmap(3, 2, wifiIcon, 10, 10, false);   // WiFi at x=3

    const uint8_t* bleIcon = bleConnected ? icon_ble_on : icon_ble_off;
    drawBitmap(16, 2, bleIcon, 10, 10, false);    // BLE at x=16

    // --- Right side: Battery icon with dynamic fill ---
    int16_t batX = DISPLAY_WIDTH - 19;  // 16px icon + 3px margin
    drawBitmap(batX, 2, icon_battery, 16, 10, false);  // White outline

    // Fill interior proportionally (white fill = charged)
    if (batteryPercent > 0) {
        uint8_t pct = batteryPercent > 100 ? 100 : batteryPercent;
        int16_t fillW = (int16_t)(BATTERY_FILL_MAX_W * pct / 100);
        if (fillW < 1) fillW = 1;
        fillRect(batX + BATTERY_FILL_X_OFFSET,
                 2 + BATTERY_FILL_Y_OFFSET,
                 fillW, BATTERY_FILL_H, false);  // false = white (inverted on black bar)
    }
}

// =====================================================================
// Widget Rendering
// =====================================================================

void DisplayManager::renderTextWidget(int16_t x, int16_t y, int16_t w, int16_t h,
                                       const char* label, const char* value,
                                       int16_t cornerRadius)
{
    if (cornerRadius > 0) {
        drawRoundRect(x, y, w, h, cornerRadius);
    } else {
        drawRect(x, y, w, h);
    }
    drawText(x + 4, y + 4, label, 1);

    // Try large font for numeric values
    if (canUseLargeFont(value)) {
        int vw = textWidthLarge(value);
        int16_t vx = x + (w - vw) / 2;
        int16_t vy = y + 16 + (h - 16 - LARGE_FONT_HEIGHT) / 2;
        drawTextLarge(vx, vy, value);
    } else {
        uint8_t scale = 2;
        int vw = textWidth(value, scale);
        int16_t vx = x + (w - vw) / 2;
        int16_t vy = y + 14 + (h - 14 - 7 * scale) / 2;
        drawText(vx, vy, value, scale);
    }
}

void DisplayManager::renderWidget(const WidgetDef& widget, const String& value)
{
    // Apply value formatting
    String displayValue = ValueFormatter::format(value, widget.valueFormat);

    // Draw widget border (rounded or sharp)
    if (widget.cornerRadius > 0) {
        drawRoundRect(widget.x, widget.y, widget.w, widget.h, widget.cornerRadius);
    } else {
        drawRect(widget.x, widget.y, widget.w, widget.h);
    }

    // Draw label at top
    drawText(widget.x + 4, widget.y + 4, widget.label.c_str(), 1);

    // Choose font based on fontSize and content
    bool useLarge = (widget.fontSize >= 32) && canUseLargeFont(displayValue.c_str());

    if (useLarge) {
        // Large number font — crisp 16px rendering
        int vw = textWidthLarge(displayValue.c_str());

        // Truncate if too wide
        while (vw > widget.w - 8 && displayValue.length() > 1) {
            displayValue = displayValue.substring(0, displayValue.length() - 1);
            vw = textWidthLarge(displayValue.c_str());
        }

        int16_t vx = widget.x + (widget.w - vw) / 2;
        int16_t vy = widget.y + 16 + (widget.h - 16 - LARGE_FONT_HEIGHT) / 2;
        drawTextLarge(vx, vy, displayValue.c_str());
    } else {
        // 5x7 font with scaling
        uint8_t scale = widget.fontSize <= 16 ? 1 : (widget.fontSize <= 24 ? 2 : 3);
        int vw = textWidth(displayValue.c_str(), scale);

        while (vw > widget.w - 6 && displayValue.length() > 1) {
            displayValue = displayValue.substring(0, displayValue.length() - 1);
            vw = textWidth(displayValue.c_str(), scale);
        }

        int16_t vx = widget.x + (widget.w - vw) / 2;
        int16_t vy = widget.y + 14 + (widget.h - 14 - 7 * scale) / 2;
        drawText(vx, vy, displayValue.c_str(), scale);
    }
}

// =====================================================================
// Layout System
// =====================================================================

void DisplayManager::setLayout(const LayoutDef& layout)
{
    _currentLayout = layout;
    _hasLayout = true;
    Serial.printf("[Display] Layout set: '%s' with %d widgets\n",
                  layout.name.c_str(), layout.widgets.size());
}

bool DisplayManager::hasLayout() const
{
    return _hasLayout;
}

void DisplayManager::renderLayout(const std::map<String, String>& dataValues,
                                   bool wifiConnected, bool bleConnected,
                                   uint8_t batteryPercent)
{
    if (!_hasLayout) return;

    clear();
    renderStatusBar(wifiConnected, bleConnected, batteryPercent);

    for (const auto& widget : _currentLayout.widgets) {
        String value = "--";
        auto it = dataValues.find(widget.dataBinding);
        if (it != dataValues.end()) {
            value = it->second;
        }
        renderWidget(widget, value);
    }

    partialRefresh();
}

bool DisplayManager::parseLayoutJson(const String& json, LayoutDef& layout)
{
    JsonDocument doc;
    if (deserializeJson(doc, json)) return false;

    layout.name = doc["name"] | "Custom";
    layout.widgets.clear();

    JsonArray widgets = doc["widgets"].as<JsonArray>();
    for (JsonObject w : widgets) {
        WidgetDef wd;
        wd.type         = w["type"] | "text";
        wd.x            = w["x"] | 0;
        wd.y            = w["y"] | 0;
        wd.w            = w["width"] | 50;
        wd.h            = w["height"] | 50;
        wd.label        = w["label"] | "";
        wd.dataBinding  = w["dataBinding"] | "";
        wd.fontSize     = w["fontSize"] | 16;
        wd.valueFormat  = w["valueFormat"] | "";
        wd.cornerRadius = w["cornerRadius"] | 0;
        layout.widgets.push_back(wd);
    }
    return true;
}

String DisplayManager::serializeLayout(const LayoutDef& layout)
{
    JsonDocument doc;
    doc["name"] = layout.name;

    JsonArray widgets = doc["widgets"].to<JsonArray>();
    for (const auto& w : layout.widgets) {
        JsonObject obj = widgets.add<JsonObject>();
        obj["type"]         = w.type;
        obj["x"]            = w.x;
        obj["y"]            = w.y;
        obj["width"]        = w.w;
        obj["height"]       = w.h;
        obj["label"]        = w.label;
        obj["dataBinding"]  = w.dataBinding;
        obj["fontSize"]     = w.fontSize;
        obj["valueFormat"]  = w.valueFormat;
        obj["cornerRadius"] = w.cornerRadius;
    }

    String json;
    serializeJson(doc, json);
    return json;
}
