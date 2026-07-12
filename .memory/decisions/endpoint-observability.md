---
title: Endpoint Observability
type: note
permalink: claudemon32/decisions/endpoint-observability
created: 2026-07-12
updated: 2026-07-12
tags:
- endpoint
- schema
- observability
- error-handling
source_sha: d86396092a9b0330d39c97e50feec71105e83f10
source_paths: docs/architecture.md
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: audit:claude-haiku-4-5
---

## Observations
- [decision] Usage endpoint `GET https://api.anthropic.com/api/oauth/usage` is **undocumented** (same one Claude Code's `/usage` panel uses). Schema parsing is **deliberately strict** with intentional failures on drift instead of best-effort parsing. #undocumented-api #risk
- [parsing] Pinned schema: `five_hour` and `seven_day` (or `seven_day_per_million`) objects with `utilization` 0–100 and `resets_at` ISO timestamps. Fallback to `limits[]` array if new format appears. Anything else trips `DRIFT` state: account renders as `DATA?`, raw JSON logged, daemon keeps running. #schema-verification #drift-detection
- [rationale] Deliberate loudness: schema changes are *noticed* (rows show `DATA?`) rather than silently half-parsed. Logged raw responses help diagnose endpoint changes immediately. #observability

## Relations
- mitigates [[Architecture Decision]]
- related_to [[OAuth & Credential Model]]
