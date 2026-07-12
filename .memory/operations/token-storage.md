---
title: Token Storage
type: note
permalink: claudemon32/operations/token-storage
created: 2026-07-12
updated: 2026-07-12
tags:
- keychain
- storage
- secrets
source_sha: d86396092a9b0330d39c97e50feec71105e83f10
source_paths: docs/architecture.md, docs/troubleshooting.md
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: audit:claude-haiku-4-5
---

## Observations
- [storage] `service:"claudemon"` — Keychain stores one generic-password item per account, accessed via `/usr/bin/security`. Path stability (not venv-relative) prevents authorization prompts during launchd daemon operation. #keychain-service
- [index] `~/.claudemon/accounts.json` (plaintext, no secrets) maps account labels to Keychain item names. Queries this index on startup; accounts with deleted Keychain items auto-prune from the index. #accounts-index
- [logs] `~/Library/Logs/claudemon/claudemon.log` (rotating: 5 MB × 3). Daemon state cache (no secrets) at `~/.claudemon/state.json`. LaunchAgent plist at `~/Library/LaunchAgents/com.claudemon.agent.plist`. #daemon-state #logging

## Relations
- implements [[OAuth & Credential Model]]
- related_to [[Project Status]]
