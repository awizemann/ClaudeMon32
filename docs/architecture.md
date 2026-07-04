# Architecture

```
Claude accounts ──OAuth PKCE──▶ claudemon CLI ──tokens──▶ macOS Keychain (service "claudemon")
      ▲                                                        │
      │  GET /api/oauth/usage (per account, every 180 s)       ▼
launchd agent (claudemon run) ──▶ {"cmd":"set_usage",...} ──▶ ESP32-S3 firmware
                                        USB serial                │
                                                                  ▼
                                                    200×200 SSD1681 e-paper
```

Two components:

- **Host** (`host/`, Python): OAuth per account, token refresh, polling,
  rendering, serial push, launchd agent. All intelligence lives here.
- **Firmware** (`esp32/firmware/`, PlatformIO/Arduino): receives `set_usage`
  and draws. Deliberately dumb — see [protocol.md](protocol.md).

## Auth model

Each monitored account gets its **own OAuth grant** (PKCE, paste-code flow
against the public Claude Code client). This is deliberate: refresh tokens
**rotate** on every refresh, so sharing a credential with Claude Code (or
between two tools) means whichever client refreshes second gets invalidated.
ClaudeMon never reads or writes Claude Code's `Claude Code-credentials`
Keychain item.

Storage: one Keychain generic-password item per account under service
`claudemon` (accessed via `/usr/bin/security`, so the Keychain ACL binds to a
stable binary — a `keyring`-style Python-path ACL breaks on every venv rebuild
and would stall the unattended agent with authorization prompts). A label
index (no secrets) lives at `~/.claudemon/accounts.json`.

`oauth.load_fresh(label)` is the **single entry point** for a live token:
load → refresh if <2 min to expiry → persist the rotated token immediately.
Errors are classified: `OAuthError` (grant dead → account shows `AUTH!`,
re-login required) vs `OAuthTransientError` (network/5xx → keep last data,
retry next cycle).

## The usage endpoint

`GET https://api.anthropic.com/api/oauth/usage` with `Authorization: Bearer`
plus `anthropic-beta: oauth-2025-04-20` — the same endpoint Claude Code's
`/usage` panel reads. It is **undocumented**. Parsing is pinned to the
verified schema (`five_hour`/`seven_day` objects with `utilization` 0–100 and
`resets_at` ISO timestamps, with the `limits[]` array as fallback). Anything
else trips a `DRIFT` state, renders as `DATA?`, and logs the raw body —
deliberately loud, so schema changes are noticed rather than half-parsed.

## Cadence

| What | How often |
|---|---|
| Poll per account | 180 s (60 s drew steady HTTP 429s with 3 accounts) |
| 429 response | back off 5 min, keep last data, don't escalate |
| Push to device | when content changed, at most every 150 s; 5-min heartbeat regardless |
| E-ink refresh | partial per push; full every 5th render or 15 min (anti-ghosting) |
| STALE banner | device-side, 10 min without a push (computed from device uptime) |

## Failure handling

| Failure | Behavior |
|---|---|
| Refresh rejected (400/401/403) | Account → `AUTH!` row; others unaffected; log hourly |
| Token endpoint 5xx / network | Transient: keep last snapshot, retry next cycle |
| Usage fetch 401 with fresh token | One forced refresh, then degrade |
| Fetch 5xx/network | Keep snapshot; `ERR` after 3 consecutive; per-account backoff |
| Schema drift | `DATA?` row, raw JSON logged, daemon keeps running |
| Device unplugged | Keep polling; serial rescan with backoff; reconnect → push |
| Keychain item deleted externally | Account pruned from the index automatically |
| Daemon dies | launchd restarts it; device flips STALE after 10 min regardless |
| Mac sleeps | launchd resumes on wake; expiry margin handles long sleeps |

## Firmware notes

- All command processing happens on the **main Arduino loop**. BLE-received
  commands are queued from the NimBLE callback (small stack; and rendering
  or mutating display state from another task would race the render loop).
- `set_usage` replies **before** rendering (e-ink refresh blocks 2–4 s).
- USB-CDC RX buffer is raised to 2048 bytes — the default 256 silently drops
  the tail of multi-account payloads that arrive as one burst.
- Logs: `~/Library/Logs/claudemon/claudemon.log` (rotating, 5 MB × 3);
  `claudemon.out` holds raw crash output captured by launchd.
