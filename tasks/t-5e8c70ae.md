---
id: t-5e8c70ae
title: Anthropic card: drop fake fields, add severity + weekly_scoped
status: done
added: 2026-07-12
---

## Description

Confirmed live (probe of all 3 accounts): the Anthropic card's plan chip, message count, and activity histogram have NO data source in the OAuth usage endpoint — they were always synthetic demo data. Real, currently-unused signals the endpoint DOES return: per-window `severity` (normal/warning/…) in limits[], and a `weekly_scoped` window (distinct from weekly_all/seven_day). Alan chose: drop the fakes, surface the real signals.

Host: usage.py parse per-window severity + weekly_scoped (limits[] kind="weekly_scoped"); add `severity` to WindowUsage; add week_scoped to AccountUsage; render._cockpit_account drops plan/msgs/act, adds severity + wk_scoped_pct, keeps wk_rnw; update docs/protocol.md set_cockpit account schema.
Firmware: Dashboard.h AccountRow drop plan/msgs/act, add severity + wkScopedPct; Protocol.cpp parse; UI.cpp fillAnthropic new layout (severity badge, 5h/week/scoped gauges, footer RESETS IN + RENEWS), remove the activity histogram panel.
Verify: host tests, then flash + on-device visual check.

## Plan



## Artifacts



