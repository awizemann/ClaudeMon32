#ifndef ICONS_H
#define ICONS_H

#include <Arduino.h>

// 10x10 1-bit icons stored in PROGMEM
// Each row is 2 bytes (10 bits used), 10 rows = 20 bytes per icon
// Bit 7 of first byte is leftmost pixel

// WiFi connected — three arcs with center dot
static const uint8_t PROGMEM icon_wifi_on[] = {
    0b00111100, 0b00,  // row 0:   ████
    0b01000010, 0b00,  // row 1:  █    █
    0b10011001, 0b00,  // row 2: █  ██  █
    0b00100100, 0b10,  // row 3:   █  █  █
    0b01011010, 0b00,  // row 4:  █ ██ █
    0b00010000, 0b10,  // row 5:    █    █ (filler)
    0b00011000, 0b00,  // row 6:    ██
    0b00011000, 0b00,  // row 7:    ██
    0b00000000, 0b00,  // row 8:
    0b00000000, 0b00,  // row 9:
};

// WiFi disconnected — X shape
static const uint8_t PROGMEM icon_wifi_off[] = {
    0b10000001, 0b00,  // row 0: █      █
    0b01000010, 0b00,  // row 1:  █    █
    0b00100100, 0b00,  // row 2:   █  █
    0b00011000, 0b00,  // row 3:    ██
    0b00011000, 0b00,  // row 4:    ██
    0b00100100, 0b00,  // row 5:   █  █
    0b01000010, 0b00,  // row 6:  █    █
    0b10000001, 0b00,  // row 7: █      █
    0b00000000, 0b00,  // row 8:
    0b00000000, 0b00,  // row 9:
};

// Bluetooth connected — rune shape
static const uint8_t PROGMEM icon_ble_on[] = {
    0b00010000, 0b00,  // row 0:    █
    0b00011000, 0b00,  // row 1:    ██
    0b01010100, 0b00,  // row 2:  █ █ █
    0b00101000, 0b00,  // row 3:   █ █
    0b00010000, 0b00,  // row 4:    █
    0b00101000, 0b00,  // row 5:   █ █
    0b01010100, 0b00,  // row 6:  █ █ █
    0b00011000, 0b00,  // row 7:    ██
    0b00010000, 0b00,  // row 8:    █
    0b00000000, 0b00,  // row 9:
};

// Bluetooth disconnected — dimmed/outline
static const uint8_t PROGMEM icon_ble_off[] = {
    0b00010000, 0b00,  // row 0:    █
    0b00010000, 0b00,  // row 1:    █
    0b00010000, 0b00,  // row 2:    █
    0b00000000, 0b00,  // row 3:
    0b00010000, 0b00,  // row 4:    █
    0b00000000, 0b00,  // row 5:
    0b00010000, 0b00,  // row 6:    █
    0b00010000, 0b00,  // row 7:    █
    0b00010000, 0b00,  // row 8:    █
    0b00000000, 0b00,  // row 9:
};

// Battery outline — 16x10 pixels, white on black status bar
// Body is 14px wide, 10px tall, with 2px nub on right for positive terminal
// Interior (x+1,y+1 to x+12,y+8) left empty for dynamic fill
//
// Pixel layout (16 wide × 10 tall):
//  ██████████████
//  █            █ ██
//  █            █ ██
//  █            █ ██
//  █            █ ██
//  █            █ ██
//  █            █ ██
//  █            █ ██
//  █            █ ██
//  ██████████████
//
static const uint8_t PROGMEM icon_battery[] = {
    0b11111111, 0b11111100,  // row 0: top edge (14px)
    0b10000000, 0b00000110,  // row 1: sides + nub
    0b10000000, 0b00000110,  // row 2: sides + nub
    0b10000000, 0b00000110,  // row 3: sides + nub
    0b10000000, 0b00000110,  // row 4: sides + nub
    0b10000000, 0b00000110,  // row 5: sides + nub
    0b10000000, 0b00000110,  // row 6: sides + nub
    0b10000000, 0b00000110,  // row 7: sides + nub
    0b10000000, 0b00000110,  // row 8: sides + nub
    0b11111111, 0b11111100,  // row 9: bottom edge (14px)
};

// Battery fill region: starts at (x+1, y+1), max width 12px, height 8px
#define BATTERY_FILL_X_OFFSET  1
#define BATTERY_FILL_Y_OFFSET  1
#define BATTERY_FILL_MAX_W    12
#define BATTERY_FILL_H         8

#endif // ICONS_H
