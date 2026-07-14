---
title: Global-token Source Discovery
type: note
permalink: claudemon32/decisions/global-token-source-discovery
created: 2026-07-12
updated: 2026-07-12
---

## Observations
- [decision] Cloudflare/GitHub (and Paddle once live) are configured with **one global API token per service**, not per-zone/per-repo manual entry (Alan, 2026-07-12). The host **discovers** available resources via the token — Cloudflare `GET /zones` (Zone:Read + Analytics:Read), GitHub `GET /user/repos` (`repo` scope) — and the web admin presents them as a **checklist**; the user selects which to show and in what order. Stored as the design's `shown{}` selection set + the token (Keychain), not a hand-curated list. #sources #config #cockpit
- [constraint] **Anthropic stays per-account OAuth** (`claudemon login`) — a different auth model (logging into accounts, not enumerating sub-resources under a token), so it is NOT part of the global-token scheme. #anthropic #oauth
- [decision] This **supersedes** the manual `add-zone`/`add-repo`/`add-product` model as the primary path; those CLI commands remain as an optional power-user fallback. Paddle discovery waits on the live Billing API (currently stubbed). Selection is still capped by the payload/screen limits (12 sites / 6 repos). #supersedes
- [todo] Implement in **Cockpit Phase 3**: add `list_zones`/`list_repos` discovery to the fetchers; store token + selection; wire the admin Sources (token) + Displays (checkbox select + order) tabs to drive the `to_cockpit_payload` inputs. #phase-3

## Relations
- refines [[Cockpit Redesign Phase]]
- relates_to [[OAuth & Credential Model]]
- relates_to [[Architecture Decision]]
