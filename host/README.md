# claudemon (host)

Monitors Claude subscription usage limits (5-hour and weekly windows) for
multiple accounts and pushes them to the ESP32 e-paper desk display over USB
serial. Personal tool; runs on this Mac only.

## Setup

```sh
cd host
uv sync
```

## Accounts

Each monitored account gets its **own OAuth grant**, stored in the macOS
Keychain under service `claudemon` — completely separate from Claude Code's
`Claude Code-credentials` item (sharing that credential would break the CLI
because refresh tokens rotate).

```sh
uv run claudemon login personal    # opens browser; paste the code#state back
uv run claudemon login work
uv run claudemon accounts
```

## Verify the data path

```sh
uv run claudemon probe personal    # raw usage endpoint response (schema check)
uv run claudemon status            # table: 5H/WEEK used + reset countdowns
```

The usage endpoint (`GET https://api.anthropic.com/api/oauth/usage`,
`Authorization: Bearer` + `anthropic-beta: oauth-2025-04-20`) is the one
Claude Code's `/usage` panel reads. It is undocumented; parsing is defensive
and `probe` exists to confirm the live schema. If parsing degrades, accounts
show `SCHEMA DRIFT` and the raw JSON is logged to
`~/Library/Logs/claudemon/claudemon.log`.

## Device

```sh
uv run claudemon push-once         # one fetch + one push (auto-detects the port)
uv run claudemon run --foreground  # 60s poll loop, pushes on change / 5-min heartbeat
```

The firmware's `set_usage` command renders up to 4 accounts with 5H/WK bars.
The device flips to a STALE banner if the host stops pushing for 10 minutes.

## Background agent

```sh
uv run claudemon install-agent    # launchd, runs at login, KeepAlive
uv run claudemon uninstall-agent
```

Logs: `~/Library/Logs/claudemon/claudemon.log`.
Non-secret state cache: `~/.claudemon/state.json` (`claudemon status --cached`).
