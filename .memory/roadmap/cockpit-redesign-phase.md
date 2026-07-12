---
title: Cockpit Redesign Phase
type: note
permalink: claudemon32/roadmap/cockpit-redesign-phase
created: 2026-07-12
updated: 2026-07-12
---

## Observations
- [handoff] New design handoff `design/design_handoff_claudemon_cockpit/` ("ClaudeMon Cockpit") supersedes the current dense 4-tab dashboard. Two surfaces: (1) **Device UI** 800×480 — Home grid (2×2 source tiles + Alerts panel) → tap tile → source page → `‹` back; (2) **Web Admin** (Sources/Displays/Alerts/Device tabs). High-fidelity: exact hex/type/spacing in the handoff README are authoritative. #design #cockpit
- [new-source] Adds **Paddle** (macOS product sales) as a 4th source alongside Anthropic/Cloudflare/GitHub — brand new, no host fetcher or payload section yet. #paddle #new-source
- [gap] Current firmware `UI.cpp` is a 4-page tab-bar/swipe UI (Claude/Cloudflare/GitHub/System); board bring-up (`board_elecrow.cpp`, LovyanGFX RGB+GT911) is **DONE and running on hardware** — the crowpanel README "STUB/scaffold" language is stale. New design is a full UI rewrite: home grid, alerts, drill-in nav, 3 Anthropic account cards + activity histogram, paginated 12 Cloudflare sites (6/page), Paddle product grid, GitHub repo list. #firmware-rewrite #stale-doc
- [DECISION-OPEN] **Topology fork — must resolve before building.** Prototype literally says admin is "served by the device (claudemon.local)" with "tokens stored encrypted on the device," implying ESP32 gains WiFi + HTTP server + on-device API polling. This CONTRADICTS the locked Mac-brain model (host owns OAuth/tokens/fetch/format, device only renders over USB serial). Option A (recommended): keep Mac-brain — admin served/owned by the Mac host, tokens stay in Keychain, host keeps fetching+formatting and pushes an enriched payload; device faithfully renders the *visual* design. Option B: device-autonomous per the prototype (throws away the working host stack; on-device OAuth refresh for Anthropic is nasty since refresh tokens rotate). Prototype's deployment topology is a prototype artifact; its visual spec is the mandate. #architecture-decision #mac-brain-vs-device
- [contract-relaxation] Design wants a per-second live clock + live reset countdowns on-device. Current host-rendering contract sends static strings (`updated` "14:32", `fh_rst` "3H14M") refreshed only on push. Live ticking needs a bounded contract relaxation: host sends epoch/seconds-remaining ints, device ticks locally. #host-rendering-contract
- [payload-growth] Enriched payload (12 CF sites + totals, 24-bar Anthropic histogram, Paddle, derived alerts) will exceed the current 8192-byte line cap — protocol needs pagination or a bigger cap. #payload-limits

## Relations
- supersedes [[CrowPanel Extension]]
- revisits [[Architecture Decision]]
- revisits [[Host-Rendering Contract]]
- affects [[Serial Protocol]]
- affects [[Hardware Targets]]
