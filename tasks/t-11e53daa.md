---
id: t-11e53daa
title: Cockpit Phase 4 (DEFERRED) — On-device autonomy: WiFi + HTTP admin + on-device fetchers + NVS
status: doing
added: 2026-07-12
priority: low
---

## Description

Umbrella for on-device autonomy (P4.0–P4.5). PROGRESS as of 2026-07-13: P4.0 (WiFi provisioning + NVS) and P4.1 (WiFi transport: device TCP server on 8781 + mDNS claudemon.local; host net_link.NetworkLink/AutoLink) are DONE and committed. Beyond the original P4.1 scope, also shipped: WiFi auto-reconnect resilience, admin mDNS name (claudemon-admin.local), OAuth account management in the admin, WiFi status icon, and the launchd agent wired to `run --device auto` (WiFi-first, serial fallback) — so the Mac-brain setup is now fully wireless and self-starting. REMAINING: P4.2 on-device HTTP admin, P4.3 on-device fetchers, P4.4 on-device Anthropic OAuth (the risky crux — device gets its own grant), P4.5 autonomy cutover. See conventions/crowpanel-header-widget-layout + the new WiFi-transport note.

## Plan



## Artifacts



