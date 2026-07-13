#include "Net.h"

#include <WiFi.h>
#include <ESPmDNS.h>
#include <Preferences.h>

// TCP port for the command protocol (distinct from the future on-device HTTP
// admin, which will use 80). Advertised over mDNS as _claudemon._tcp.
static const uint16_t CMD_PORT   = 8781;
static const char*    MDNS_HOST  = "claudemon";        // -> claudemon.local
static const size_t   MAX_RX     = 16384;              // matches the protocol cap
static const char*    NVS_NS     = "claudemon";

static Preferences    s_prefs;
static WiFiServer     s_server(CMD_PORT);
static WiFiClient     s_client;
static NetLineHandler s_handler   = nullptr;
static String         s_rx;
static bool           s_servicesUp = false;

static void startServices() {
    // Bring up the TCP server + mDNS once, on first association.
    s_server.begin();
    s_server.setNoDelay(true);
    if (MDNS.begin(MDNS_HOST)) {
        MDNS.addService("claudemon", "tcp", CMD_PORT);
        Serial.printf("[NET] mDNS: %s.local, cmd port %u\n", MDNS_HOST, CMD_PORT);
    } else {
        Serial.println("[NET] mDNS start failed");
    }
    s_servicesUp = true;
}

void net_init(NetLineHandler handler) {
    s_handler = handler;
    s_prefs.begin(NVS_NS, /*readOnly=*/false);
    String ssid = s_prefs.getString("wifi_ssid", "");
    String pass = s_prefs.getString("wifi_pass", "");

    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);   // keep the TCP server responsive
    if (ssid.length()) {
        Serial.printf("[NET] connecting to '%s'...\n", ssid.c_str());
        WiFi.begin(ssid.c_str(), pass.c_str());
    } else {
        Serial.println("[NET] no WiFi creds stored; provision with set_wifi");
    }
}

void net_set_wifi(const String& ssid, const String& pass) {
    s_prefs.putString("wifi_ssid", ssid);
    s_prefs.putString("wifi_pass", pass);
    Serial.printf("[NET] stored creds for '%s'; reconnecting\n", ssid.c_str());
    WiFi.disconnect(/*wifioff=*/false);
    WiFi.begin(ssid.c_str(), pass.c_str());
}

bool net_wifi_up() { return WiFi.status() == WL_CONNECTED; }

String net_ip() { return net_wifi_up() ? WiFi.localIP().toString() : String(); }

void net_loop() {
    static bool wasUp = false;
    bool up = net_wifi_up();
    if (up && !wasUp) {
        Serial.printf("[NET] WiFi up, IP %s\n", WiFi.localIP().toString().c_str());
        if (!s_servicesUp) startServices();
    } else if (!up && wasUp) {
        Serial.println("[NET] WiFi lost");
    }
    wasUp = up;
    if (!up || !s_servicesUp) return;

    // Single active command client at a time (the host pushes serially). A new
    // connection replaces a stale one.
    if (!s_client || !s_client.connected()) {
        WiFiClient incoming = s_server.available();
        if (incoming) {
            s_client = incoming;
            s_rx = "";
        }
    }

    while (s_client && s_client.available()) {
        char ch = (char)s_client.read();
        if (ch == '\n' || ch == '\r') {
            if (s_rx.length()) {
                if (s_handler) s_handler(s_rx, s_client);
                s_rx = "";
            }
        } else {
            s_rx += ch;
            if (s_rx.length() > MAX_RX) {
                s_client.println("[WARN] RX line exceeded cap; dropped");
                s_rx = "";
            }
        }
    }
}
