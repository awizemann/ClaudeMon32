---
title: OAuth & Credential Model
type: note
permalink: claudemon32/architecture/oauth-credential-model
created: 2026-07-12
updated: 2026-07-12
tags:
- auth
- security
- keychain
- oauth
source_sha: d86396092a9b0330d39c97e50feec71105e83f10
source_paths: docs/architecture.md
source_paths_inferred: false
reviewed: 2026-07-12
reviewed_by: audit:claude-haiku-4-5
---

## Observations
- [decision] Each monitored account gets its **own OAuth grant** (PKCE, public client, paste-code flow against the public Claude Code client ID). This is deliberate: refresh tokens **rotate** on every refresh. Sharing credentials between tools or accounts means whichever client refreshes second gets invalidated. ClaudeMon never reads/writes Claude Code's own Keychain items. #credential-isolation #rotation-safety
- [storage] One Keychain generic-password item **per account** under service `"claudemon"` (accessed via `/usr/bin/security` so ACL binds to a stable binary, not a Python path that breaks on venv rebuild). A plaintext JSON index at `~/.claudemon/accounts.json` maps labels to Keychain entries (no secrets in the index). #keychain-service #accounts-index
- [operation] Single entry point: `oauth.load_fresh(label)` loads, refreshes if <2 min to expiry, persists rotated token immediately. Errors classified as `OAuthError` (grant dead → account shows `AUTH!`, re-login required) or `OAuthTransientError` (network/5xx → keep last data, retry next cycle). #error-classification #recovery

## Relations
- stores_in [[Token Storage]]
- related_to [[Endpoint Observability]]
