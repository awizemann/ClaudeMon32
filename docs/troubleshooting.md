# Troubleshooting

## Device not showing up on USB

`ls /dev/cu.usbmodem*` empty? In rough order of likelihood:

1. **Charge-only cable.** The classic. Use a known data cable.
2. **Board is powered off.** This board has a PWR button (GPIO18) — short-press
   it. If the e-paper shows nothing at all, the board isn't running.
3. **Force download mode:** hold **BOOT** while plugging in. If it *still*
   doesn't enumerate (`system_profiler SPUSBDataType` shows nothing), the
   cable/port/board is at fault — the ESP32-S3 ROM bootloader always
   enumerates when power and data lines are good.
4. The port name varies: native-USB S3 boards appear as `usbmodem*`; boards
   with a CP210x/CH340 bridge appear as `usbserial*`/`SLAB*`/`wchusbserial*`.
   ClaudeMon scans all of these.

## "Port is busy" when flashing

The background agent holds the serial port open. Stop it first:

```sh
claudemon uninstall-agent
pio run -t upload --upload-port /dev/cu.usbmodem<YOURS>   # or esptool
claudemon install-agent
```

## The screen flashes black/white — is it rebooting?

No. That's the e-paper **full refresh** (anti-ghosting), which runs every 5th
update or 15 minutes. A real reboot shows the mascot boot screen. Between full
refreshes, updates use quiet partial refreshes; mild ghosting between full
refreshes is normal for SSD1681 panels.

## STALE banner

The host hasn't pushed for 10+ minutes. Check, in order:

```sh
claudemon status                 # can the host fetch at all?
launchctl print gui/$UID/com.claudemon.agent | head -5   # agent running?
tail -20 ~/Library/Logs/claudemon/claudemon.log
```

Common causes: Mac was asleep (recovers on its own within ~3 min of waking),
device was unplugged (auto-reconnects), agent not installed.

## A row shows AUTH!

That account's refresh token was rejected — the grant is dead (password
change, revocation, or the token was refreshed by another client). Re-login:

```sh
claudemon login <label>
```

The running agent picks the new credentials up within a poll cycle — no
restart needed.

## A row shows DATA? (or numbers look wrong)

The undocumented usage endpoint returned a shape the parser doesn't
recognize. Inspect it:

```sh
claudemon probe <label>          # dumps the raw response
```

The raw body is also logged to `~/Library/Logs/claudemon/claudemon.log`.
Open an issue with the (redacted) shape — the parser is deliberately strict
so drift is loud instead of silently rendering wrong numbers.

## HTTP 429 in the logs

The usage endpoint rate-limits. ClaudeMon polls every 3 minutes per account
and backs off 5 minutes on a 429, which has been clean for 3 accounts. If you
monitor many accounts and see sustained 429s, raise `POLL_INTERVAL_S` in
`host/src/claudemon/daemon.py`.

## Logging into a second account stores the first one again

Browsers silently reuse the signed-in claude.ai session. Log in to each
additional account from a **private/incognito window** (copy the printed URL
into one), or log out of claude.ai first. `claudemon login` warns you if the
new grant resolves to an organization it has already stored.

## Where things live

| Thing | Path |
|---|---|
| Tokens | macOS Keychain, service `claudemon` (one item per account) |
| Account label index | `~/.claudemon/accounts.json` (no secrets) |
| Daemon state cache | `~/.claudemon/state.json` (no secrets) |
| Logs | `~/Library/Logs/claudemon/claudemon.log` (+ `.out` for crashes) |
| LaunchAgent | `~/Library/LaunchAgents/com.claudemon.agent.plist` |
