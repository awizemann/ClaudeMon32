# Serial Protocol & Device Commands

The host and firmware speak **newline-delimited JSON** over USB-CDC serial at **115200 baud** (nominal — native USB). This is the stable interface: reimplement the display side on any hardware and the host tool works unchanged [[memophant/conventions/serial-protocol]].

## Framing rules

- One JSON object per line, terminated by `\n` (also accepts `\r`)
- Max line length is **per-firmware**: 2048 bytes (e-paper), 8192 bytes (CrowPanel), 16384 bytes (Cockpit)
- Firmware **logs on the same port** (`[INIT] ...`, `[BLE RX] ...`); hosts must skip non-JSON lines
- Responses echo the command name: `{"status":"ok","cmd":"<name>",...}`
- Errors are `{"status":"error","msg":"..."}`
- On connect, send a bare `\n` first; discard any error reply (terminates a stale partial line)
- Allow ≥3 s response timeout (device is blocked 2–4 s during e-ink refresh)

## Commands

### `ping`

```json
→ {"cmd":"ping"}
← {"status":"ok","cmd":"pong"}
```

Used for port discovery: the host globs `/dev/cu.usbmodem*` and picks the port that answers.

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
| `updated` | string | Host-rendered wall-clock time ("HH:MM") |
| `label` | string | Account name, uppercase, ≤10 chars (5×7 font is caps-only) |
| `fh_pct` | int | 5-hour utilization 0–100; **-1 = unknown** (renders `--`) |
| `fh_rst` | string | Host-rendered countdown ("2H05M", "44M") |
| `wk_pct` | int | Weekly utilization 0–100; -1 = unknown |
| `wk_rnw` | string | Host-rendered renewal, human-readable ("WED 8PM") |
| `st` | string | `ok` \| `auth` (re-login needed) \| `err` (fetch failures) \| `drift` (schema drift) |

Design invariants:

- **The host renders every string.** Device does no clock math, no timezone handling, no formatting — it draws labels and bars from integers, nothing else [[memophant/conventions/host-rendering-contract]].
- Max **4 accounts** per payload; extras ignored.
- Reply is sent **before** the screen redraws (rendering is deferred to the device's main loop), so the host never waits on e-ink.
- Data is **ephemeral** — not persisted on the device. After a reboot, the device shows its boot screen until the next push.
- Device stamps each push with its own uptime; if no push arrives for **10 minutes**, it overlays a STALE banner.

### `set_dashboard` — the CrowPanel payload

The 5" Elecrow CrowPanel (ESP32-S3, 800×480, LVGL) uses a richer payload with Cloudflare zones and GitHub repos alongside Claude usage. Line length cap is raised to **8192 bytes**.

```json
→ {"cmd":"set_dashboard","params":{
     "updated":"14:32",
     "claude":[{...}],         // same as set_usage accounts[]
     "cloudflare":[
       {"zone":"EXAMPLE.CO","req":"1.2M","bw":"4.2GB","cache":98,
        "spark":[65,77,58,89,79,100,82],"codes":[95,2,2,1],"st":"ok"}
     ],
     "github":[
       {"repo":"AWIZEMANN/CLAUDEMON3","stars":"1.2K","forks":"48",
        "rel":"v2.1.0","ci":"pass","push":"3h","st":"ok"}
     ]}}
← {"status":"ok","cmd":"set_dashboard","msg":"dashboard updated"}
```

**Cloudflare zones** (`cloudflare[]`):

| Field | Type | Meaning |
|---|---|---|
| `zone` | string | Zone name, uppercase, ≤10 chars |
| `req` / `bw` | string | Host-formatted requests / bandwidth ("1.2M", "4.2GB") |
| `cache` | int | Cache-hit % 0–100; **-1 = unknown** |
| `spark` | int[] | Request trend 0–100 (host-normalized); `[]` = none |
| `codes` | int[] | HTTP mix: `[2xx%, 3xx%, 4xx%, 5xx%]` |
| `st` | string | `ok` \| `auth` \| `err` |

**GitHub repos** (`github[]`):

| Field | Type | Meaning |
|---|---|---|
| `repo` | string | `OWNER/REPO`, uppercase, ≤20 chars |
| `stars` / `forks` / `issues` / `prs` | string | Host-formatted counts; `""` = unknown |
| `rel` / `push` / `lang` | string | Release tag / last-push age / language; `""` = unknown |
| `ci` | string | `pass` \| `fail` \| `run` \| `""` |
| `st` | string | `ok` \| `auth` \| `err` |

Invariants (as in `set_usage`): host renders all strings; max 4 Claude rows, 6 zones, 6 repos; reply before render; ephemeral; STALE after 10 min.

### `set_cockpit` — Cockpit redesign payload

The Cockpit redesign (`set_cockpit`) replaces tabs with a Home grid + four drill-down pages. Payload is larger and introduces **live-tick** fields (device increments them 1/s between pushes). Line length raised to **16384 bytes** [[memophant/roadmap/cockpit-redesign-phase]].

Top-level fields include `updated`, `base` (live-tick: seconds since local midnight), `date`, `anthropic` (accounts with new `fh_sec` live-tick field, plan, msgs, activity histogram), `cloudflare`, `paddle` (new: sales/products), `github`, and `alerts` (derived, severity-sorted).

Key invariant: only `base` and each account's `fh_sec` carry raw time for live-tick display. The device increments/decrements these 1/s between pushes. Every other string remains host-formatted and static — no other logic lives on the device.

## Transport notes

- Firmware handles USB-CDC and **BLE** (Nordic UART Service) identically
- Host discovers ports by pinging `/dev/cu.usbmodem*` glob
- Firmware gates TX on DTR; opening with DTR deasserted silences responses
- Firmware queues BLE-received commands to its main loop before processing