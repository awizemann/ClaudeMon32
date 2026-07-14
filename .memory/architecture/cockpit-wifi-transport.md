---
title: Cockpit WiFi Transport
type: note
permalink: claudemon32/architecture/cockpit-wifi-transport
created: 2026-07-13
updated: 2026-07-13
source_sha: 3ca83a309062565bb3b81a01d0e8d8b836395b3d
source_paths: esp32/crowpanel/src/Net.cpp, host/src/claudemon/net_link.py, host/src/claudemon/launchd.py, host/src/claudemon/admin.py
source_paths_inferred: false
---

Shipped in the WiFi-transport session (P4.0/P4.1 and beyond). Still Mac-brain — the host fetches/formats/pushes; this only changes the wire between host and panel and how they find each other. Full device autonomy (P4.2+) is still ahead.

## Observations
- [fact] The panel is driven over WiFi OR USB serial through the SAME newline-JSON protocol: the device runs a TCP command server on port 8781 (Net.cpp), advertised over mDNS as claudemon.local; the host's net_link.NetworkLink mirrors DeviceLink over TCP. #wifi #transport
- [decision] `claudemon run --device auto` (net_link.AutoLink) tries WiFi first (claudemon.local) then falls back to USB serial, re-preferring WiFi on each reconnect; the launchd agent runs --device auto so the panel self-drives after a reboot with no IP/config. #agent #fallback
- [decision] The web admin advertises itself over mDNS as claudemon-admin.local (admin.py + zeroconf), distinct from the panel's claudemon.local, so no IP is needed. `.local` (mDNS) is LAN-wide; `.localhost` is loopback-only and can't serve other devices. #mdns #admin
- [gotcha] WiFi is provisioned via a `set_wifi` command (creds to NVS, never in source) over USB serial or the admin's Device tab. The device needs WiFi.setAutoReconnect + a periodic reconnect nudge + mDNS re-advertise on reassociation, or band-steering on a combined 2.4/5 GHz SSID drops it and it never returns. #provisioning #resilience
- [constraint] The device TCP server holds a single client; a restarted daemon can briefly fall back to serial until the device's stale client clears (self-heals; a clean reboot has none). #limitation

## Relations
- relates_to [[Architecture Decision]]
- relates_to [[Cockpit Redesign Phase]]
- relates_to [[Serial Protocol]]
