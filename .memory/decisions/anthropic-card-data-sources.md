---
title: Anthropic Card Data Sources
type: note
permalink: claudemon32/decisions/anthropic-card-data-sources
created: 2026-07-13
updated: 2026-07-13
source_sha: 3ca83a309062565bb3b81a01d0e8d8b836395b3d
source_paths: host/src/claudemon/usage.py, host/src/claudemon/render.py
source_paths_inferred: false
---

Decided while reworking the Anthropic account card: show only what the OAuth usage endpoint actually returns, after probing all three live accounts.

## Observations
- [decision] The Anthropic card shows only fields the OAuth usage endpoint actually returns: the 5h + weekly + weekly_scoped windows, per-window server severity, and extra-usage credits (spend). #anthropic #cockpit
- [gotcha] The endpoint has NO plan tier, message count, or per-hour activity series — those were demo-only fixtures and were removed from the card and the device. Don't reintroduce them without a real source. #anthropic #no-source
- [fact] Real fields: five_hour/seven_day (utilization + resets_at); limits[] entries (kind = session|weekly_all|weekly_scoped, percent, severity, is_active); spend (used/limit in minor units, enabled). The seven_day_opus/_sonnet model windows are always null across accounts. #anthropic #schema

## Relations
- relates_to [[Endpoint Observability]]
