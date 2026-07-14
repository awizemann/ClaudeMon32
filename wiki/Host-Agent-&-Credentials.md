---
source_sha: 78e7991be79b8b70a53133bfdbae3fea34bc4cb5
source_paths: host/src/claudemon/daemon.py, host/src/claudemon/oauth.py, host/src/claudemon/keychain.py
source_paths_inferred: false
---

# Host Agent & Credentials

The host daemon (`host/src/claudemon/daemon.py` + `host/src/claudemon/oauth.py`) manages OAuth refresh, polling, rendering, serial communication, and the launchd background agent.

## Token refresh model

Each account has a grant issued against the public Claude Code client ID, stored in the macOS Keychain (service `claudemon`, one generic-password item per account).

The single entry point is `oauth.load_fresh(label)` (from `host/src/claudemon/oauth.py`):

```python
token = oauth.load_fresh(label)  # loads from keychain, refreshes if <2 min to expiry
```

On refresh:

1. Token is loaded from Keychain → Keychain ACL is bound to `/usr/bin/security` (stable, works across venv rebuilds)
2. If <2 min to expiry, hit the token endpoint to get a fresh one
3. Refresh tokens **rotate** — save the new token immediately back to Keychain
4. Return the live access token

Errors are classified:

- `OAuthError` (class defined at `host/src/claudemon/oauth.py:37`) — grant is dead (password changed, revoked, or used by another client). Account shows `AUTH!` on the display; user must re-login.
- `OAuthTransientError` — network/5xx; keep the last snapshot, retry next cycle.

## The daemon loop

`daemon.py`'s `AccountRunner` class (`host/src/claudemon/daemon.py:27`) is the per-account poller:

Multiple `AccountRunner` instances run concurrently, each polling every 180 s, so 4 accounts poll independently and don't stall each other.

The main daemon:

1. Polls all accounts in parallel
2. Renders a fresh `set_usage` or `set_dashboard` payload
3. Pushes to the device over USB-CDC (or waits for reconnect with backoff)
4. Heartbeats every 5 min regardless
5. Logs state to `~/Library/Logs/claudemon/claudemon.log` (rotating)

## Keychain storage

Tokens live in the macOS Keychain under:

```
Service: claudemon
Account: <label>  (e.g., "personal", "work")
Kind: generic password
Data: {"access_token": "...", "refresh_token": "...", "expires_at": 1234567890}
```

The label index (no secrets) is cached at `~/.claudemon/accounts.json`:

```json
{"personal": {...}, "work": {...}}
```

Access is via `/usr/bin/security` (the standard Keychain CLI), which avoids Python path ACL issues that plague venv'd tools. The ACL binds to `/usr/bin/security`'s stable hash, so the Keychain persists across venv rebuilds [[memophant/operations/token-storage]].

## Launchd agent

The background agent runs under the user's login session:

```
~/Library/LaunchAgents/com.claudemon.agent.plist
```

`claudemon install-agent` writes this plist, which launchd loads at login. On crash or wake-from-sleep, launchd restarts the daemon. To update the daemon, stop the agent:

```sh
claudemon uninstall-agent
# update the tool via uv
claudeemon install-agent
```

Logs: `~/Library/Logs/claudemon/claudemon.log` (rotating, max 5 MB × 3) and `~/Library/Logs/claudemon/claudemon.out` (raw stderr, captured by launchd).

## State cache

The daemon persists its last snapshot at `~/.claudemon/state.json`:

```json
{
  "personal": {
    "fh_pct": 12,
    "fh_rst": "3H14M",
    "wk_pct": 63,
    "wk_rnw": "WED 8PM",
    "status": "ok"
  },
  ...
}
```

This is **not** persisted on the device (the device is stateless). `claudemon status --cached` reads this file instead of polling.

## Failure recovery

| Failure | Recovery |
|---|---|
| Token endpoint 5xx | Retry next cycle with last snapshot |
| Usage endpoint 401 | One forced refresh, then show `AUTH!` if still fails |
| Schema drift | Log the raw response, show `DATA?`, keep running |
| Device unplugged | Serial rescan with backoff; reconnect → push |
| Mac sleep | launchd resumes on wake; token expiry margin (2 min) handles long sleeps |
| Keychain locked | Prompt once per session (typical); failure is per-account |