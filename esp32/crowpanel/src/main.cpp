// ClaudeMon CrowPanel Cockpit firmware — entry point.
//
// Receives newline-delimited JSON on UART0 (via the CH340) and renders the
// Cockpit UI with LVGL: a Home grid (2x2 source tiles + alerts panel) drilling
// into four source pages. Same protocol as before plus `set_cockpit`
// (../../docs/protocol.md). All data/formatting/secrets stay on the host; this
// device only lays out and draws — plus the ONE sanctioned local-time behavior:
// it ticks the header clock and counts each 5h reset down once per second
// between pushes (it can't call the host in between).
#include <Arduino.h>
#include <lvgl.h>

#include "board_config.h"
#include "Dashboard.h"
#include "Net.h"
#include "Protocol.h"
#include "UI.h"

static const size_t   MAX_LINE = 16384;           // matches the Cockpit protocol cap
static const uint32_t STALE_MS = 10UL * 60 * 1000;

static Dashboard g_dash;
static String    g_rx;
static bool      g_pendingRender = false;
static uint32_t  g_lastPushMs    = 0;
static bool      g_staleShown    = false;

// 1 Hz LVGL timer: tick the header clock + reset countdowns locally. Mutates
// labels only (never rebuilds) so it can't leak objects or timers. Gated behind
// the UI's live/paused flag (default live).
static void tick1hz(lv_timer_t*) {
    ui_tick_1hz();
    ui_set_wifi(net_wifi_up());   // reflect WiFi association in the header icon
}

// Dispatch one command line and write the reply to `out` — Serial for the USB
// path, the WiFiClient for the TCP path (both are Print). The Dashboard is
// shared global state, so either transport can drive the display.
static void handleLine(const String& line, Print& out) {
    String trimmed = line;
    trimmed.trim();
    if (trimmed.isEmpty()) return;   // bare '\n' the host sends on (re)connect

    bool updated = false;
    String reply = Protocol::handle(trimmed, g_dash, updated);

    // Reply BEFORE rendering — the LVGL repaint can take a beat and the host
    // waits on this line (matched by echoed cmd).
    out.println(reply);

    if (updated) {
        g_pendingRender = true;
        g_lastPushMs = millis();
    }
}

void setup() {
    Serial.begin(115200);
    delay(200);
    Serial.println("[INIT] ClaudeMon CrowPanel Cockpit starting");

    platform_lvgl_init();
    ui_init();

    // Local live-tick — one shared LVGL timer for the clock + all countdowns.
    lv_timer_create(tick1hz, 1000, nullptr);

    // WiFi transport (additive; serial keeps working). Joins WiFi if provisioned.
    net_init(handleLine);

    Serial.println("[INIT] Ready.");
}

void loop() {
    // Drain the serial RX into a line buffer.
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            if (g_rx.length()) {
                handleLine(g_rx, Serial);
                g_rx = "";
            }
        } else {
            g_rx += c;
            if (g_rx.length() > MAX_LINE) {
                // Overlong line — almost certainly corrupt; drop it so we
                // resync on the next newline instead of parsing garbage.
                Serial.println("[WARN] RX line exceeded cap; dropped");
                g_rx = "";
            }
        }
    }

    // WiFi transport: drain any TCP client and dispatch through the same handler.
    net_loop();

    platform_lvgl_tick();

    // Render is deferred out of handleLine so the reply goes first.
    if (g_pendingRender) {
        ui_update(g_dash);
        g_pendingRender = false;
    }

    // STALE overlay from device uptime (host heartbeats every 5 min).
    if (g_dash.valid) {
        bool stale = (millis() - g_lastPushMs) > STALE_MS;
        if (stale != g_staleShown) {
            ui_set_stale(stale);
            g_staleShown = stale;
        }
    }
}
