// Cockpit UI (LVGL 8.3). Board-neutral — only lv_* calls, no hardware.
//
// A Home grid (2x2 source tiles + an alerts panel) drills into four source
// pages — Anthropic, Cloudflare, Paddle, GitHub. The header `‹` returns home.
// Transitions are instant show/hide (no animation) per the RGB-panel bandwidth
// constraint. The whole tree is rebuilt on each set_cockpit; between pushes only
// the live-tick labels (header clock + per-account RESETS-IN) are mutated in
// place (no rebuild) to avoid per-second heap churn.
#pragma once

#include "Dashboard.h"

void ui_init();                       // build the static chrome + boot screen
void ui_update(const Dashboard& d);   // repaint from a fresh payload

// 1 Hz live tick: advance the header clock from `base` and count each account's
// RESETS-IN down. No-op when paused or before the first payload. Mutates labels
// only — never rebuilds — so it can't leak objects/timers.
void ui_tick_1hz();
void ui_set_live(bool live);          // gate live ticking (default live)

void ui_set_stale(bool stale);        // overlay the STALE banner
void ui_set_brightness(uint8_t pct);  // 0-100 dim overlay (100 = no dim)
void ui_set_wifi(bool connected);     // show/hide the header WiFi icon
