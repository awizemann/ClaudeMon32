---
source_sha: 78e7991be79b8b70a53133bfdbae3fea34bc4cb5
source_paths: host/src/claudemon, esp32/app/EPaperManager
source_paths_inferred: false
---

# Architecture Overview

ClaudeMon splits intelligence cleanly across two components:

```
Claude accounts ──OAuth PKCE──▶ claudemon CLI ──tokens──▶ macOS Keychain (service "claudemon")
      ▲                                                        │
      │  GET /api/oauth/usage (per account, every 180 s)       ▼
launchd agent (claudemon run) ──▶ {"cmd":"set_usage",...} ──▶ ESP32-S3 firmware
                                        USB serial                │
                                                                  ▼
                                                    200×200 SSD1681 e-paper
```

## Components

### Host (Python daemon)

The host (`host/src/claudemon/`) runs on your Mac and owns:

- **OAuth & credential management** — Each account gets its own PKCE grant, stored in the macOS Keychain under service `claudemon`. Refresh tokens rotate on every refresh; this separation keeps ClaudeMon independent from Claude Code's own credential [[memophant/architecture/oauth-credential-model]].
- **Polling** — Fetches each account's usage every 180 seconds (3 min). This cadence was chosen empirically: 60 s with 3 accounts drew sustained HTTP 429s; 180 s is clean [[memophant/architecture/e-paper-display-integration]]. On a 429, backs off 5 min, keeps the last snapshot, doesn't escalate.
- **String rendering** — Computes human-readable strings: `"WED 8PM"` for the weekly reset, `"3H14M"` for the 5-hour countdown, account names, status badges. The device does **none** of this — no clock math, no timezone handling, no formatting [[memophant/conventions/host-rendering-contract]].
- **Serial push** — Writes a single JSON object per line over USB-CDC (115200 baud), waits for the device reply.
- **Launchd agent** — Runs at login, restarted by launchd on crash or wake-from-sleep.
- **Keychain interface** — Via `/usr/bin/security` (stable, no Python path ACLs) for both login and token refresh [[memophant/operations/token-storage]].

### Firmware (Arduino, ESP32-S3)

The firmware (`esp32/app/EPaperManager/`) is deliberately simple:

- Receives a `set_usage` or `set_dashboard` command over USB-CDC or BLE (Nordic UART Service) [[memophant/conventions/serial-protocol]]
- Parses the JSON payload
- Renders it to the 200×200 SSD1681 e-paper panel [[memophant/architecture/hardware-targets]]
- Replies `{"status":"ok","cmd":"set_usage",...}` immediately (before the e-ink refresh completes)
- Computes and overlays a STALE banner if 10+ minutes pass without a push

No secrets, no network calls, no credentials, no logic. A device that cannot be compromised because it has nothing to compromise.

## Credential model

Each monitored Claude account gets its **own OAuth grant** — a deliberate choice [[memophant/architecture/oauth-credential-model]]. The endpoint session tokens rotate on every refresh, so sharing one token between two clients (ClaudeMon and Claude Code) would invalidate whichever one refreshes second.

The flow:

1. `claudemon login <label>` — opens a browser to claude.ai, you authenticate, copy the code off the page
2. ClaudeMon exchanges it for tokens using the public Claude Code client ID, PKCE, and your local state
3. Tokens go into the Keychain under `service: "claudemon", account: "<label>"`
4. The host loads and refreshes them via `oauth.load_fresh(label)` — the single entry point for a live token

Errors are classified: `OAuthError` means the grant is dead (password change, revocation); `OAuthTransientError` means network/5xx (keep last data, retry). A dead grant shows `AUTH!` on the display; you re-login and the agent picks it up within one cycle.

## Polling & failure handling

| Scenario | Behavior |
|---|---|
| Account token rejected (400/401/403) | Row → `AUTH!`; others unaffected; log hourly |
| Token endpoint 5xx or network | Transient: keep last snapshot, retry next cycle |
| Usage fetch 5xx/network | Keep snapshot; `ERR` after 3 consecutive; per-account backoff |
| Schema drift (endpoint shape change) | `DATA?` row, raw JSON logged, daemon keeps running |
| Device unplugged | Keep polling; serial rescan with backoff; reconnect → push |
| Mac sleeps | launchd resumes on wake; token expiry margin handles long sleeps |

The STALE banner is device-side: if no push arrives for 10 minutes, the firmware overlays it. This ensures the display never silently lies.

## Cadence

| Event | Frequency |
|---|---|
| Poll per account | 180 s (3 min) |
| 429 response | Back off 5 min, keep last data |
| Push to device | When content changed, or at most every 150 s; 5-min heartbeat regardless |
| E-ink full refresh | Every 5th render or 15 min (anti-ghosting) |
| STALE banner | Device-side, 10 min without a push |

The host heartbeats every 5 minutes even when nothing changed — so if you're watching the display, you know the data is fresh (or STALE if the Mac is asleep).

## The usage endpoint

`GET https://api.anthropic.com/api/oauth/usage` with `Authorization: Bearer` and `anthropic-beta: oauth-2025-04-20` — the same endpoint Claude Code's `/usage` panel reads. It is **undocumented** [[memophant/decisions/endpoint-observability]].

Parsing is deliberately strict, pinned to the verified schema:
```
{
  "five_hour": { "utilization": 0–100, "resets_at": "<ISO8601>" },
  "seven_day": { "utilization": 0–100, "resets_at": "<ISO8601>" },
  "limits": [ ... ]  // fallback, for compatibility
}
```

Anything else triggers a `DRIFT` state: the raw response is logged, and the row shows `DATA?` instead of silently wrong numbers. This is deliberate — schema changes are loud, not silent.

## Serial protocol

Host and firmware communicate via **newline-delimited JSON** over USB-CDC (115200 baud, nominal — native USB). The protocol is minimal and stable [[memophant/conventions/serial-protocol]]:

- One JSON command per line, max 2048 bytes (e-paper firmware) or 8192 bytes (CrowPanel)
- Firmware replies before rendering (e-ink refresh blocks 2–4 s)
- Device is blocked 2–4 s during e-ink refresh; allow ≥3 s response timeout
- Log lines from the device (`[INIT] ...`, `[BLE RX] ...`) are interspersed; hosts skip non-JSON

See [Serial Protocol & Device Commands](Serial-Protocol-Device-Commands).