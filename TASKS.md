# Tasks

> Repo-resident task board managed by Memophant and Claude sessions. Move items between
> sections as work progresses; checklist state mirrors the section.

## Ideas


## Todo

- [ ] Cockpit: deliver brightness to the panel (firmware field) (id: t-72793ade) (added: 2026-07-12)
- [ ] Cockpit: Home-tile page order + enable (design screen 07) (id: t-286cbe0b) (added: 2026-07-12)
- [ ] P4.2 — On-device HTTP admin (serve admin.html + JSON API from NVS) (id: t-cfe46b0e) (added: 2026-07-13)
- [ ] P4.3 — On-device fetchers (Cloudflare/GitHub/Paddle in C++) (id: t-ddd03e87) (added: 2026-07-13)
- [ ] P4.4 — On-device Anthropic OAuth (device's own grant; the crux) (id: t-3ece4121) (added: 2026-07-13)
- [ ] P4.5 — Autonomy cutover (on-device poll loop, Mac-optional, NVS persistence) (id: t-53cec871) (added: 2026-07-13)
- [ ] Fix collapsed header status pill (same flex trap as the WiFi icon) (id: t-0e9adea6) (added: 2026-07-13) (priority: low)
- [ ] Device: drop stale TCP client so a restarted daemon reconnects over WiFi faster (id: t-52b8a3a4) (added: 2026-07-13) (priority: low)
- [ ] Wiki: document WiFi transport, admin OAuth/WiFi provisioning, and claudemon-admin.local (id: t-f8a407ed) (added: 2026-07-13) (priority: low)
- [ ] Admin persistence: launchd agent so claudemon-admin.local is always up (id: t-e293f383) (added: 2026-07-13) (priority: low)

## Doing

- [ ] Cockpit Phase 4 (DEFERRED) — On-device autonomy: WiFi + HTTP admin + on-device fetchers + NVS (id: t-11e53daa) (added: 2026-07-12) (priority: low)

## Done

- [x] Device reboots ~every 15 min: WiFi-stack heap-corruption panic (esf_buf_recycle/ppTask) (id: t-1315af5a) (added: 2026-07-13) (priority: high)
- [x] Anthropic card: drop fake fields, add severity + weekly_scoped (id: t-5e8c70ae) (added: 2026-07-12)
- [x] P4.1 — WiFi transport (device TCP server + mDNS; host TCP push) (id: t-d580cf64) (added: 2026-07-13)
- [x] P4.0 — NVS + WiFi provisioning (set_wifi serial cmd, creds in NVS) (id: t-3e436953) (added: 2026-07-13)
- [x] Tune CrowPanel RGB panel display jitter (Cockpit UI) (id: t-da02e6ba) (added: 2026-07-12)
- [x] Cockpit Phase 3 — Config schema + Web Admin (host-served now, portable to device) (id: t-77c118a0) (added: 2026-07-12)
- [x] Cockpit Phase 2 — Firmware UI rewrite to the Cockpit design (home grid + drill-in) (id: t-44834934) (added: 2026-07-12)
- [x] Cockpit Phase 1 — Host data model + enriched protocol (Paddle, alerts, live-tick) (id: t-9b2f23bb) (added: 2026-07-12) (priority: high)

## Archived

