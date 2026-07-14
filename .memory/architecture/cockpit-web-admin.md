---
title: Cockpit Web Admin
type: note
permalink: claudemon32/architecture/cockpit-web-admin
created: 2026-07-12
updated: 2026-07-12
source_sha: eca43cc639b4e89a613b4281516a70f4720c015e
source_paths: host/src/claudemon/admin.py, host/src/claudemon/admin.html, host/src/claudemon/config.py, host/src/claudemon/cli.py
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: claude-opus-4-8
---

The Phase-3c config console (on the `cockpit-redesign` branch). Source: host/src/claudemon/admin.py, admin.html, config.py, cli.py.

## Observations
- [decision] Config admin is **host-served**: `claudemon admin` runs a stdlib `ThreadingHTTPServer` (default `0.0.0.0:8770`), reachable from any LAN browser — NOT device-served yet. It is a single self-contained `admin.html` (inline CSS/JS, zero external requests) + a 3-route JSON API (`GET /api/state`, `POST /api/token`, `POST /api/config`) built so the SAME page + contract port onto the ESP32's own HTTP server in Phase 4. #admin #phase-4-ready
- [decision] Security posture: single-user, **no auth**, trusted-LAN (matches the design). Tokens are NEVER returned by any GET and never logged — only written inbound to the Keychain via `POST /api/token`. `--host 127.0.0.1` restricts to the Mac. Verified live with real tokens: none leak in `/api/state` or the page. #security #tokens
- [convention] The admin writes the SAME stores the daemon reads — Keychain (tokens) + `config.py` (selection + settings) — so edits take effect on the daemon's next poll; there is no separate apply/push step. #config
- [gotcha] Selection is tri-state: absent = show all discovered, `[]` = show none, list = that subset in order. The page collapses a fully-checked list back to `null` so it re-persists as "show all". #tri-state
- [todo] Brightness persists but does nothing until a firmware payload field carries it to the backlight; the design's Home-tile page-order/enable (screen 07) has no host-config model yet. #follow-up

## Relations
- part_of [[Cockpit Redesign Phase]]
- implements [[Global-token Source Discovery]]
- relates_to [[OAuth & Credential Model]]
