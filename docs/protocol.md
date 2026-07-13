# Serial Protocol

The host and firmware speak **newline-delimited JSON** over USB-CDC serial at
**115200 baud** (the baud is nominal — it's native USB). This is the stable
interface: reimplement the firmware side on any display hardware and the host
tool works unchanged.

## Framing rules

- One JSON object per line, terminated by `\n` (`\r` also accepted).
- Maximum line length is **per-firmware**: **2048 bytes** on the e-paper board
  (`set_usage`), **8192 bytes** on the CrowPanel (`set_dashboard`), and
  **16384 bytes** on the Cockpit firmware (`set_cockpit`). Longer lines are
  truncated by the firmware's buffer cap and will fail to parse — match the
  command to the target (see each command's *Line length* note).
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

### `set_dashboard` — the CrowPanel payload

The 5" Elecrow CrowPanel (ESP32-S3, 800×480, LVGL) uses a richer payload that
adds Cloudflare and GitHub sections alongside Claude usage. Same framing rules;
the device renders it as a dense tile dashboard.

```json
→ {"cmd":"set_dashboard","params":{
     "updated":"14:32",
     "claude":[
       {"label":"PERSONAL","fh_pct":12,"fh_rst":"3H14M",
        "wk_pct":63,"wk_rnw":"WED 8PM (3D)","st":"ok"}
     ],
     "cloudflare":[
       {"zone":"EXAMPLE.CO","req":"1.2M","bw":"4.2GB","cache":98,"vis":"12K","thr":"41",
        "spark":[65,77,58,89,79,100,82],"codes":[95,2,2,1],"st":"ok"}
     ],
     "github":[
       {"repo":"AWIZEMANN/CLAUDEMON3","stars":"1.2K","forks":"48","watch":"14",
        "issues":"12","prs":"3","rel":"v2.1.0","ci":"pass","push":"3h","lang":"Python","st":"ok"}
     ]}}
← {"status":"ok","cmd":"set_dashboard","msg":"dashboard updated"}
```

The `claude[]` rows are **identical** to `set_usage`'s `accounts[]` (same fields,
same meaning). The new sections:

| Field | Type | Meaning |
|---|---|---|
| `zone` | string | Cloudflare zone display name, uppercase, ≤10 chars |
| `req` / `bw` / `vis` / `thr` | string | Requests / bandwidth / unique visitors / threats — **host-formatted** (`"1.2M"`, `"4.2GB"`, `""` = unknown) |
| `cache` | int | Cache-hit % 0–100 (bar); **-1 = unknown** |
| `spark` | int[] | Request trend, each **0–100** (host-normalized to the series peak); drawn as a line chart. `[]` = none |
| `codes` | int[] | HTTP status mix as whole-percent `[2xx,3xx,4xx,5xx]`; drawn as a segmented bar. `[]` = none |
| `repo` | string | `OWNER/REPO`, uppercase, ≤20 chars |
| `stars` / `forks` / `watch` / `issues` / `prs` | string | Compact counts; `""` = unknown (issue/PR split needs a GitHub token) |
| `rel` / `push` / `lang` | string | Latest release tag / last-push relative age (`"3h"`) / primary language; `""` = unknown |
| `ci` | string | Default-branch CI: `pass` \| `fail` \| `run` \| `""` (unknown) — drawn as a colored pill |
| `st` | string | `ok` \| `auth` (token missing/rejected) \| `err` (fetch failure) — per source row |

Design invariants (unchanged from `set_usage`):

- **The host renders every string.** Counts arrive pre-formatted; the device
  only draws them plus bars from the integer `*_pct` / `cache` fields.
- Caps: **4** Claude rows, **6** Cloudflare zones, **6** GitHub repos; extras ignored.
- Reply is sent **before** the LVGL redraw.
- Data is **ephemeral** — not persisted; boot screen shows until the first push.
- STALE overlay after **10 minutes** without a push (device-side, from uptime).

Because color framebuffers can't be pushed over serial, the CrowPanel firmware
**owns rendering** (LVGL). This is the one deliberate departure from the e-paper
firmware's "draw exactly what the host says" model — the host still owns all
data, formatting, secrets, and business logic; the device owns only layout.

> **Line length:** this payload can exceed the e-paper firmware's 2048-byte cap
> (4 accounts + 6 zones + 6 repos ≈ 2 KB). The CrowPanel firmware raises its
> RX/line buffer to **8192 bytes**. A host pushing `set_dashboard` to the small
> e-paper board would have the line truncated — send `set_usage` there instead.

### `set_cockpit` — the Cockpit payload (redesigned 800×480 UI)

The "Cockpit" redesign replaces the dense tab dashboard with a Home grid
(2×2 source tiles + an alerts panel) that drills into four source pages —
**Anthropic**, **Cloudflare**, **Paddle** (new), **GitHub**. One enriched
payload carries every screen. `set_dashboard` stays valid until the Phase 2
firmware switches; a host targeting the old firmware sends `set_dashboard`.

Keys are **abbreviated** to keep the line under the cap with worst-case data
(see *Line length* below). Every count/label is host-formatted exactly as in
`set_dashboard`; the only additions are the two sanctioned numeric-time fields
(`base`, `fh_sec` — see *Live-tick deviation*).

```json
→ {"cmd":"set_cockpit","params":{
     "updated":"14:32",
     "base":52325,
     "date":"Sun 12 Jul",
     "anthropic":{"accounts":[
       {"label":"WORK","fh_pct":88,"fh_rst":"1H02M","fh_sec":3720,
        "wk_pct":74,"wk_rnw":"WED 8PM (3D)","ws_pct":81,"sev":"warning",
        "cred":"$0.03 / $250","actv":"week","st":"ok"}
     ]},
     "cloudflare":{
       "totals":{"req":"4.28M","bw":"312GB","threats":"18.4K","cache":94},
       "down":1,"degraded":1,
       "sites":[
         {"dom":"blog.wizemann.com","req":"350K","bw":"1.3GB",
          "spark":[65,77,58,89,79,100,82],"st":"degraded"},
         {"dom":"legacy.wizemann.com","req":"","bw":"","spark":[],"st":"down"}
       ]},
     "paddle":{
       "totals":{"rev_today":"$1,248","rev_month":"$98,720","sales":"5.1K",
                 "custs":"15K","mom":"+12%"},
       "products":[
         {"name":"PixelPeek","cat":"Utilities","buys":"1.3K","custs":"4.1K",
          "rev":"$38,540","spark":[70,75,80,85,90,95,100],"st":"ok"}
       ]},
     "github":{
       "summary":{"repos":6,"issues":"96","prs":"18"},
       "repos":[
         {"name":"claudemon","owner":"awizemann","lang":"C++","lcol":"#8FBF7F",
          "stars":"342","issues":"12","prs":"3","push":"2h","st":"ok"}
       ]},
     "alerts":[
       {"lvl":0,"tag":"CRITICAL","time":"now","msg":"legacy.wizemann.com is offline","src":"Cloudflare"}
     ]}}
← {"status":"ok","cmd":"set_cockpit","msg":"cockpit updated"}
```

**Top-level params**

| Field | Type | Meaning |
|---|---|---|
| `updated` | string | Host-rendered "HH:MM" of the last push (fallback when the device isn't ticking) |
| `base` | int | **Live-tick:** seconds since **local midnight** at push time; the device increments it 1/s and formats the header clock itself |
| `date` | string | Host-rendered header date ("Sun 12 Jul") |
| `anthropic.accounts[]` | array | ≤ **3** account cards |
| `cloudflare.totals` | object | Combined totals strip (req/bw/threats/cache) |
| `cloudflare.down` / `degraded` | int | Count of shown sites that are down / degraded (tile sub-caption) |
| `cloudflare.sites[]` | array | ≤ **12** site rows; firmware paginates 6/page |
| `paddle.totals` | object | Combined sales totals |
| `paddle.products[]` | array | ≤ **4** product cards |
| `github.summary` | object | `{repos:int, issues:str, prs:str}` |
| `github.repos[]` | array | ≤ **6** repo rows |
| `alerts[]` | array | ≤ **8** derived alerts, host-sorted CRITICAL→WARNING→INFO |

**`anthropic.accounts[]`**

| Field | Type | Meaning |
|---|---|---|
| `label` | string | Account name, uppercase, ≤10 chars |
| `fh_pct` | int | 5-hour utilization 0–100; **-1 = unknown** |
| `fh_rst` | string | Host-rendered 5h countdown ("1H02M"); "" unknown |
| `fh_sec` | int | **Live-tick:** integer seconds to the 5h reset; the device counts it down. **-1 = unknown**, 0 = elapsed |
| `wk_pct` | int | Weekly (overall / `weekly_all`) utilization 0–100; -1 unknown |
| `wk_rnw` | string | Host-rendered weekly renewal ("WED 8PM (3D)") |
| `ws_pct` | int | Scoped-weekly (`weekly_scoped`) utilization 0–100; **-1 = unknown/absent** |
| `sev` | string | Worst server-reported severity across the account's windows (`"warning"` / `"critical"` / `"exceeded"`); **`""` = normal/none → no badge**. Server-authoritative, from the usage endpoint's `limits[]`. |
| `cred` | string | Extra-usage credits, host-formatted ("$0.03 / $250", or "$0.03" uncapped); **`""` = disabled → line hidden** |
| `actv` | string | Which window the server marks currently-binding (`is_active`): `"5h"` \| `"week"` \| `"scoped"` \| `""`. The device accents that gauge. |
| `st` | string | `ok` \| `auth` \| `err` \| `drift` |

> Note: the usage endpoint exposes no plan tier, message count, or per-hour
> activity series (verified across accounts), so the card carries none — earlier
> `plan`/`msgs`/`act` fields were demo-only and were removed. The model-scoped
> weekly windows (`seven_day_opus`/`_sonnet`/…) exist in the schema but are
> always null for these accounts, so they are not surfaced.

**`cloudflare.totals`** — `req`/`bw`/`threats` are host-formatted strings ("" unknown); `cache` is an int 0–100 (**-1 unknown**), a request-weighted hit ratio.

**`cloudflare.sites[]`**

| Field | Type | Meaning |
|---|---|---|
| `dom` | string | Domain, ≤24 chars (device ellipsizes) |
| `req` / `bw` | string | Host-formatted requests / bandwidth; "" unknown |
| `spark` | int[] | Request trend, each 0–100 (host-normalized). `[]` = none |
| `st` | string | Origin health: `up` \| `degraded` \| `down`. A fetch/auth failure reads `down`; an OK zone with ≥20% non-2xx/3xx reads `degraded` |

**`paddle.totals`** — `rev_today`/`rev_month` host-formatted money, `sales`/`custs` host-formatted counts, `mom` a signed percent string ("+12%"); all "" unknown.

**`paddle.products[]`**

| Field | Type | Meaning |
|---|---|---|
| `name` | string | Product name, ≤20 chars |
| `cat` | string | Category ("Utilities"); "" unknown |
| `buys` / `custs` | string | Host-formatted purchases / customers; "" unknown |
| `rev` | string | Host-formatted month revenue; "" unknown |
| `spark` | int[] | Revenue trend 0–100. `[]` = none |
| `st` | string | `ok` \| `auth` \| `err` |

**`github.repos[]`**

| Field | Type | Meaning |
|---|---|---|
| `name` / `owner` | string | Repo / owner, split from `owner/repo`, ≤24 chars each |
| `lang` | string | Primary language; "" unknown |
| `lcol` | string | Language-dot hex hint ("#8FBF7F"); "" when unknown (device uses its muted default) |
| `stars` / `issues` / `prs` | string | Host-formatted counts; "" unknown |
| `push` | string | Host-rendered last-push relative age ("2h"); "" unknown |
| `st` | string | `ok` \| `auth` \| `err` |

**`alerts[]`** — derived host-side from live data + admin toggles (site down → CRITICAL; degraded, if the 4xx toggle is on → WARNING; account 5h ≥ threshold → WARNING; a watched repo's open issues → INFO). Sorted CRITICAL→WARNING→INFO, stable within a level.

| Field | Type | Meaning |
|---|---|---|
| `lvl` | int | Severity: `0` critical, `1` warning, `2` info (drives sort + color) |
| `tag` | string | Level tag text ("CRITICAL"/"WARNING"/"INFO") |
| `time` | string | Host-rendered relative age ("now") |
| `msg` | string | Host-rendered alert message |
| `src` | string | Originating source ("Cloudflare"/"Anthropic"/"GitHub") |

**Live-tick deviation (the ONE sanctioned relaxation).** The Cockpit device
ticks a per-second header clock and counts each 5h reset down locally, so it
can't sit on a static string that only refreshes on the next push. Two — and
only two — fields carry raw time for that: `base` (seconds since local
midnight, the clock seed) and each account's `fh_sec` (seconds to the 5h
reset). The device increments `base` and decrements `fh_sec` once per second
between pushes; every other string stays host-formatted exactly as today. This
is necessary because the device can't call back to the host between pushes —
without it the clock and countdowns would freeze until the next refresh. All
data, secrets, business logic, and every other string remain host-owned.

**Line length.** The Cockpit payload is larger (3 accounts + 24-bucket
histograms + 12 sites + 4 products + 6 repos + up to 8 alerts). The cap is
raised to **16384 bytes**; the Phase 2 firmware raises its RX/line buffer to
match. Worst-case realistic data serializes to well under 5 KB, so the cap
holds comfortably. A host must not send `set_cockpit` to firmware still on the
8192-byte `set_dashboard` buffer.

Other invariants are unchanged from `set_dashboard`: reply before the LVGL
redraw; ephemeral (not persisted); STALE overlay after 10 minutes without a
push.

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
