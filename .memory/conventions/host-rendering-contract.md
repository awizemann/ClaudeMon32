---
title: Host-Rendering Contract
type: note
permalink: claudemon32/conventions/host-rendering-contract
created: 2026-07-12
updated: 2026-07-12
tags:
- firmware
- rendering
- invariant
source_sha: d86396092a9b0330d39c97e50feec71105e83f10
source_paths: docs/protocol.md
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: audit:claude-haiku-4-5
---

## Observations
- [convention] The device firmware **never** performs clock math, timezone math, string formatting, or count scaling. The host computes and sends pre-rendered strings: `fh_rst` ('3H14M'), `wk_rnw` ('WED 8PM'), `updated` ('14:32'), and pre-formatted counts ('1.2M', '4.2GB'). Firmware only draws labels, progress bars from integers, and literal strings. #non-negotiable
- [invariant] In `set_usage` and `set_dashboard`, all text fields (`label`, `fh_rst`, `wk_rnw`, `updated`, `zone`, `req`, `bw`, `spark`, `ci`, etc.) are **host-rendered**; integers (`fh_pct`, `cache`, `codes[]`) are raw percentages/counts for bar/chart rendering. Firmware draws exactly what it receives. #payload-contract

## Relations
- enforced_by [[Architecture Decision]]
- describes [[Serial Protocol]]
