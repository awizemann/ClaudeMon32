// WiFi transport for the Cockpit (Phase 4.0/4.1).
//
// Adds a second delivery path for the same newline-JSON command protocol the
// device already speaks over USB serial: the device joins WiFi (creds persisted
// in NVS, provisioned via the `set_wifi` command), advertises itself over mDNS
// as `claudemon.local`, and runs a small TCP server that dispatches received
// lines through the SAME handler as serial — the reply is written back to the
// TCP client. Serial keeps working unchanged; WiFi is purely additive.
//
// This is the transport only. The Mac stays the brain (fetch/format/push) until
// the later autonomy phases (on-device admin/fetchers/OAuth) land.
#pragma once

#include <Arduino.h>

// Dispatch one received command line, writing the reply to `reply` (Serial for
// the USB path, the WiFiClient for the TCP path — both are Arduino Print).
typedef void (*NetLineHandler)(const String& line, Print& reply);

// Load WiFi creds from NVS and begin connecting (async) if present; remember the
// handler for TCP-delivered lines. Safe to call once from setup().
void net_init(NetLineHandler handler);

// Service WiFi state changes and drain any TCP client bytes. Call every loop().
void net_loop();

// Persist new WiFi creds to NVS and (re)connect. Returns immediately; the join
// completes asynchronously (poll net_wifi_up / net_ip).
void net_set_wifi(const String& ssid, const String& pass);

bool   net_wifi_up();   // STA associated + got an IP
String net_ip();        // dotted-quad IP, or "" when not connected
