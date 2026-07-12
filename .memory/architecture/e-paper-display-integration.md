---
title: E-paper Display Integration
type: note
permalink: claudemon32/architecture/e-paper-display-integration
created: 2026-07-12
updated: 2026-07-12
tags:
- e-paper
- ssd1681
- refresh
- cadence
source_sha: d86396092a9b0330d39c97e50feec71105e83f10
source_paths: docs/architecture.md, docs/protocol.md
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: audit:claude-haiku-4-5
---

## Observations
- [cadence] Poll per account every **180 s** (3 min). Empirically, 60 s with 3 accounts drew sustained HTTP 429s; 180 s is stable. On 429 response: back off 5 min, keep last data, don't escalate. #polling-interval
- [cadence] Push to device when content changed, at most every **150 s**; **5-min heartbeat** regardless (to update countdown timers). E-ink refresh: partial per push, full refresh every **5th** render or **15 min** (anti-ghosting). #push-interval
- [stale-detection] Device displays **STALE** banner if no push for **10 minutes** (computed from device uptime). Daemon heartbeats every 5 min even if nothing changed, so STALE should not appear unless the host is actually down. #stale-banner #heartbeat
- [error-handling] Device buffer is **2048 bytes**. Lines longer than this truncate silently and fail to parse. Firmware USB-CDC RX buffer explicitly raised to 2048 from default 256 to accept multi-account bursts. #buffer-constraint

## Relations
- related_to [[Serial Protocol]]
- constrains [[Architecture Decision]]
