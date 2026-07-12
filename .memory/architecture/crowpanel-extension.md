---
title: CrowPanel Extension
type: note
permalink: claudemon32/architecture/crowpanel-extension
created: 2026-07-12
updated: 2026-07-12
tags:
- crowpanel
- dashboard
- lvgl
- cloudflare
- github
source_sha: d86396092a9b0330d39c97e50feec71105e83f10
source_paths: docs/protocol.md
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: audit:claude-haiku-4-5
---

## Observations
- [payload] `set_dashboard` command (newer than `set_usage`): enriched payload adds Cloudflare analytics (zones, requests, bandwidth, cache %), GitHub repository stats (stars, forks, PRs, CI status), alongside Claude usage in the same format. Same **host-rendering** contract: pre-formatted counts, status strings, sparklines already normalized. #new-command #dashboard
- [limits] Max **4 Claude rows**, **6 Cloudflare zones**, **6 GitHub repos** per payload (extras ignored). Line length can reach ~2 KB, so CrowPanel firmware raises RX/line buffer to **8192 bytes**. Sending `set_dashboard` to e-paper board with its 2048-byte cap would truncate. #payload-limits #buffer-size
- [rendering] CrowPanel firmware **owns rendering** (LVGL layout engine) — deliberate departure from e-paper's 'draw exactly what host says' model. Host still owns all data, formatting, credentials, business logic; device owns only LVGL layout and color rendering. #rendering-model #departure
- [status-fields] Each Cloudflare zone and GitHub repo reports status `st`: `ok` | `auth` (token missing/rejected) | `err` (fetch failure). Sparkline and HTTP-codes-bar fields support per-zone analytics, CI status shows as colored pill (`pass` | `fail` | `run` | `""`) #status-reporting #analytics

## Relations
- extends [[Serial Protocol]]
- extends [[Architecture Decision]]
- targets [[Hardware Targets]]
