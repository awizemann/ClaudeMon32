# Troubleshooting

## Device not showing up on USB

`ls /dev/cu.usbmodem*` is empty?

1. **Use a data cable** — Charge-only cables are the #1 cause. Test with a known data cable.
2. **Power the board** — This board has a PWR button (GPIO18). Press it. If the e-paper is completely blank, the board isn't running.
3. **Force download mode** — Hold **BOOT** while plugging in. If it *still* doesn't enumerate (`system_profiler SPUSBDataType` shows nothing), the cable/port/board is at fault.
4. **Port name varies** — ClaudeMon scans `usbmodem*`, `usbserial*`, `SLAB*`, `wchusbserial*`. All variants should work.

See [Hardware & Flashing](Hardware-Flashing) for more detail.

## "Port is busy" when flashing

The background agent holds the serial port open. Stop it first:

```sh
claudeemon uninstall-agent
# flash the board
pio run -t upload --upload-port /dev/cu.usbmodem<YOURS>
# or: esptool --chip esp32s3 --port /dev/cu.usbmodem* write_flash 0x0 ...
claudeemon install-agent
```

## The screen flashes black/white — is it rebooting?

No. That's the e-paper **full refresh** (anti-ghosting), running every 5th update or 15 minutes. A real reboot shows the mascot boot screen. Between full refreshes, updates use quiet partial refreshes; mild ghosting is normal.

## STALE banner on the display

The host hasn't pushed for 10+ minutes. Diagnose:

```sh
claudeemon status               # Can the host fetch at all?
launchctl print gui/$UID/com.claudemon.agent | head -5   # Is the agent running?
tail -20 ~/Library/Logs/claudemon/claudemon.log
```

Common causes:

- **Mac was asleep** → recovers on its own within ~3 min of waking
- **Device unplugged** → auto-reconnects when plugged back in
- **Agent not installed** → run `claudemon install-agent`

## A row shows AUTH!

That account's refresh token was rejected — the grant is dead (password changed, revoked, or the token was used by another client). Re-login:

```sh
claudeemon login <label>
```

The daemon picks up the new credentials within one poll cycle — no restart needed.

## A row shows DATA? (or numbers look wrong)

The usage endpoint returned a response shape the parser doesn't recognize. Inspect it:

```sh
claudeemon probe <label>          # Dumps the raw response
```

The raw body is also logged to `~/Library/Logs/claudemon/claudemon.log`. Open an issue with the (redacted) shape — the parser is strict by design so schema changes are loud [[memophant/decisions/endpoint-observability]].

## HTTP 429 in the logs

The usage endpoint rate-limits. ClaudeMon polls every 3 minutes per account and backs off 5 minutes on a 429 [[memophant/architecture/e-paper-display-integration]]. If you monitor many accounts and see sustained 429s, raise `POLL_INTERVAL_S` in `host/src/claudemon/daemon.py`.

## Logging into a second account stores the first one again

Browsers silently reuse the signed-in claude.ai session. Log in to each additional account from a **private/incognito window** (copy the printed URL into one), or log out of claude.ai first. `claudemon login` warns you when the new grant resolves to an account it already has.

## Where things live

| Thing | Path |
|---|---|
| Tokens | macOS Keychain, service `claudemon` (one item per account) |
| Account index | `~/.claudemon/accounts.json` (no secrets) |
| Daemon state | `~/.claudemon/state.json` (no secrets) |
| Logs | `~/Library/Logs/claudemon/claudemon.log` (rotating, max 5 MB × 3) |
| LaunchAgent | `~/Library/LaunchAgents/com.claudemon.agent.plist` |
| Raw stderr | `~/Library/Logs/claudemon/claudemon.out` (captured by launchd) |