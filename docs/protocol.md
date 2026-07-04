# Serial Protocol

The host and firmware speak **newline-delimited JSON** over USB-CDC serial at
**115200 baud** (the baud is nominal — it's native USB). This is the stable
interface: reimplement the firmware side on any display hardware and the host
tool works unchanged.

## Framing rules

- One JSON object per line, terminated by `\n` (`\r` also accepted).
- Maximum line length **2048 bytes**; longer lines are truncated by the
  firmware's buffer cap and will fail to parse.
- The firmware prints **log lines on the same port** (`[INIT] ...`,
  `[BLE RX] ...`). Hosts must skip any line that doesn't parse as JSON.
- Responses echo the command name: `{"status":"ok","cmd":"<name>", ...}`.
  Errors are `{"status":"error","msg":"..."}` (no `cmd` field). Match replies
  by the echoed `cmd` — a stale error emitted while the device was busy in an
  e-ink refresh can otherwise be misattributed to the wrong command.
- On (re)connect, send a bare `\n` first and discard any error reply: it
  terminates a stale partial line left by an interrupted prior session.
- The device may be blocked for 2–4 s during an e-ink refresh; it drains its
  RX buffer (2048 bytes) afterwards. Allow a ≥3 s response timeout.

## Commands

### `ping`

```json
→ {"cmd":"ping"}
← {"status":"ok","cmd":"pong"}
```

Used for port discovery: the host globs `/dev/cu.usbmodem*` and picks the port
that answers a ping.

### `set_usage` — the ClaudeMon payload

```json
→ {"cmd":"set_usage","params":{
     "updated":"14:32",
     "accounts":[
       {"label":"PERSONAL","fh_pct":12,"fh_rst":"3H14M",
        "wk_pct":63,"wk_rnw":"WED 8PM","st":"ok"},
       {"label":"WORK","fh_pct":-1,"fh_rst":"",
        "wk_pct":-1,"wk_rnw":"","st":"auth"}
     ]}}
← {"status":"ok","cmd":"set_usage","msg":"usage updated"}
```

| Field | Type | Meaning |
|---|---|---|
| `updated` | string | Host-rendered wall-clock time shown in the header ("HH:MM") |
| `label` | string | Account name, uppercase, ≤10 chars (5×7 font is caps-only) |
| `fh_pct` | int | 5-hour window utilization 0–100; **-1 = unknown** (renders `--`) |
| `fh_rst` | string | Host-rendered countdown to the 5-hour reset ("2H05M", "44M") |
| `wk_pct` | int | Weekly window utilization 0–100; -1 = unknown |
| `wk_rnw` | string | Host-rendered weekly renewal, human readable ("WED 8PM") |
| `st` | string | `ok` \| `auth` (re-login needed) \| `err` (fetch failures) \| `drift` (schema surprise) |

Design invariants:

- **The host renders every string.** The device does no clock math, no
  timezone handling, no formatting — it draws labels, bars from integers, and
  pre-rendered strings. Keep it that way in ports.
- Maximum **4 accounts** per payload; extras are ignored.
- The reply is sent **before** the screen redraws (rendering is deferred to
  the device's main loop) so the host never waits on the e-ink.
- Usage data is **ephemeral** — not persisted on the device. After a reboot
  the device shows its boot screen until the next push.
- The device stamps each push with its own uptime; if no push arrives for
  **10 minutes** it overlays a STALE banner. Push at least that often (the
  host heartbeats every 5 minutes even when nothing changed).

### Legacy commands

The firmware retains the original e-paper-manager commands (`get_status`,
`get_config`, `set_wifi`, `set_layout`, `set_api`, `set_audio`) from the
project this repo grew out of. They still work but ClaudeMon doesn't use them;
`set_usage` takes display priority once received.

## Transport notes

- Commands also arrive over **BLE** (Nordic UART Service); the firmware queues
  BLE-received commands to its main loop before processing, so both transports
  behave identically.
- The host opens the port with default DTR/RTS asserted. The device's USB-CDC
  gates its transmit on DTR — opening with DTR deasserted silences all
  responses (learned the hard way).
