---
title: Project Status
type: note
permalink: claudemon32/project/project-status
created: 2026-07-12
updated: 2026-07-12
tags:
- status
- releases
- known-issues
source_sha: d86396092a9b0330d39c97e50feec71105e83f10
source_paths: README.md, docs/troubleshooting.md, docs/architecture.md
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: audit:claude-haiku-4-5
---

## Observations
- [maturity] Stable releases published (prebuilt firmware images available). Dual-board support: original e-paper (1.54" mono SSD1681) + newer CrowPanel (5" color LVGL with Cloudflare/GitHub integrations). #dual-target
- [known-limitation] Endpoint may change or stop working at any time (undocumented API). User must log in again if refresh token is invalidated by another client (tokens rotate on each refresh). Device shows `STALE` if host stops pushing for 10 min; STALE is not a crash, just 'data is stale'. #undocumented-api #token-sharing #stale-detection
- [rate-limits] Endpoint rate-limits: ClaudeMon polls every 3 min per account and backs off 5 min on HTTP 429. Sustained 429s with many accounts may require raising `POLL_INTERVAL_S` in `host/src/claudemon/daemon.py`. #rate-limiting #tuning

## Relations
- related_to [[Endpoint Observability]]
- related_to [[Hardware Targets]]
