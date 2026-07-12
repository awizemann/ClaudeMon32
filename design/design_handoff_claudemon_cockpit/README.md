# Handoff: ClaudeMon Cockpit

A digital development cockpit for an always-on desk display. It surfaces live status
from four sources — **Anthropic** (Claude usage), **Cloudflare** (site analytics),
**Paddle** (product sales), and **GitHub** (repos) — behind a home grid with an alerts
panel, plus a browser-hosted **Web Admin** for configuration.

---

## Overview

The product has **two surfaces**:

1. **Device UI** — the 800×480 touchscreen the user looks at all day. Home grid →
   tap a tile → drill into a source page → `‹` returns home. An alerts panel on the
   home screen aggregates issues across all sources.
2. **Web Admin** — a configuration page served locally by the device (e.g.
   `http://claudemon.local/admin`), opened from any browser on the LAN. It sets auth
   tokens, chooses which items/pages show, and tunes alerts + device settings. **Admin
   settings drive the device** (hidden items disappear, brightness dims the panel,
   the usage threshold changes which alerts fire).

## About the Design Files

The files in this bundle are **design references created in HTML** — an interactive
prototype showing intended look and behavior. They are **not production code to ship
directly**. The task is to recreate these designs in the real target environments:

- **Device UI → firmware.** Target is a **CrowPanel Advance 5.0** ESP32 board running
  **LVGL 8** (C/C++). Recreate each screen with LVGL objects/styles. The prototype's
  measurements, colors, and type scale map 1:1 to what LVGL can render (see the
  original *ClaudeMon Display — Design Spec*, which this design was built against).
- **Web Admin → a local web page.** Recreate as a small self-contained page served by
  the device's HTTP server (plain HTML/CSS/JS, or whatever the firmware toolchain
  bundles). No heavy framework needed; it is a single-user config console.

If you prefer to prototype the device UI in a framework first (React/Canvas) before
porting to LVGL, the HTML file runs as-is in a browser — open `ClaudeMon Cockpit.dc.html`.

## Fidelity

**High-fidelity.** Final colors, typography, spacing, layout, and interactions.
Recreate the device screens pixel-accurately at 800×480. All hex values, font sizes,
and pixel measurements below are authoritative.

---

## Hardware & canvas constraints (from the device spec)

- **Resolution:** 800×480 landscape. Design and build to this exact rectangle.
- **Theme:** single **dark** theme, always-on. No light mode on device.
- **Font:** **Montserrat** (LVGL bitmap font), four sizes only — adding sizes/weights
  costs flash. Sizes: **28 / 20 / 16 / 14 px**. Weights used: 700 (bold), 600
  (semibold), 400 (regular). Enable tabular/lining figures where numbers align.
- **Touch:** single-touch only. No pinch/multi-touch. Keep interactive targets
  **≥ 44×44 px**.
- **Motion:** state changes are **instant** (color/opacity), not animated. Page changes
  are instant swaps. The only allowed subtle motion is a "live" status dot pulse.
- **RGB565 caveat:** panel is 5/6/5 bits per channel. **Avoid smooth gradients** (they
  band visibly) and near-identical shades. Use flat fills. (The prototype's outer
  "studio" background gradient is *presentation chrome only* — it is NOT on the device
  screen and must not be recreated in firmware.)
- **Margins:** ~10–11 px screen padding.

---

## Design Tokens

### Device palette (use these exact hex values on the panel)

| Token            | Hex       | Use |
|------------------|-----------|-----|
| Background       | `#0B0F14` | Screen background |
| Tile             | `#161C24` | Cards / tiles / buttons |
| Sunk             | `#0E141B` | Recessed panels (alerts panel, lists, stat wells) |
| Border / line    | `#202834` | 1px borders between/around tiles |
| Divider (subtle) | `#161C24` | Row separators inside lists |
| Text             | `#E6EDF3` | Primary text, values |
| Muted            | `#8B98A5` | Secondary text, labels |
| Faint            | `#6B7885` | Captions, timestamps, axis labels |
| Faint-2          | `#5A6673` | Bezel etch text |
| Track            | `#2A3441` | Progress-bar tracks, toggle "off" |
| **Accent**       | `#D08770` | Brand wordmark, back button, primary buttons, active states, Anthropic hue |
| Good             | `#8FBF7F` | Healthy status, positive values, Paddle hue |
| Blue             | `#6AA0D8` | Info, weekly bar, PRs, Cloudflare hue |
| Amber / warn     | `#E0B25A` | Warnings, threats, stars, GitHub hue |
| Critical / red   | `#BF616A` | Offline / critical alerts |

Accent is user-tweakable in the prototype (options `#D08770` default, `#6AA0D8`,
`#8FBF7F`, `#E0B25A`); source hues (Anthropic terracotta, Cloudflare blue, Paddle
green, GitHub amber) stay fixed for identity.

### Typography scale

| Role                              | Size | Weight |
|-----------------------------------|------|--------|
| Page titles / brand wordmark      | 28px (prototype uses 24–26 in header to fit) | 700 |
| Big stat numbers (tile headline)  | 30–34px | 700 |
| Card / account headings           | 19–20px | 600 |
| Body, stat values, list rows      | 16px | 400/600 |
| Captions, tab labels, legends, timestamps | 14px (11–13 for the smallest micro-labels) | 400/600 |

Uppercase micro-labels (e.g. `ALERTS`, `RESETS IN`, `API TOKEN`) use ~11–12px with
letter-spacing `.06–.12em`, color faint/muted.

### Radius & spacing

- Radius: tiles/cards `14px`, inner tiles/list-cards `12px`, small buttons/chips
  `8–10px`, pills/dots `999px`, progress bars `5px`.
- Gaps: `10px` between tiles on device, `14–20px` in admin.
- Screen padding: `11px`. Header height: `52px`.
- Device bezel (presentation only): `#05080B` casing, 20px padding, 24px radius, screen
  inset with `inset 0 0 0 1px #161C24`.

### Status → color mapping

- `up` / operational → Good `#8FBF7F`
- `degraded` → Amber `#E0B25A`
- `down` / offline → Critical `#BF616A`
- Alert levels: `CRITICAL` red, `WARNING` amber, `INFO` blue.

---

## Screens / Views

### Chrome (all device screens)

- **Header**, 52px tall, bottom border `#161C24`.
  - **Home variant:** left = `CLAUDEMON` wordmark (26px/700, accent). Right = status
    pill (dot + text on `#161C24` pill) + clock (18px) over date (11px faint).
  - **Page variant:** left = **back button** (44×40, `#161C24` tile, accent `‹` glyph,
    24px) + page title (24px/700) over subtitle (13px muted). Right = **LIVE** indicator
    (7px pulsing dot + `LIVE`/`PAUSED` label, good/faint) + clock (18px).
- **Home-return:** the back button `‹` returns to the home grid from any page.
- **Brightness overlay:** a full-screen black layer with opacity `(100−brightness)/100 × 0.5`
  sits above content (pointer-events none) so the Admin brightness setting visibly dims
  the panel. In firmware this maps to the actual backlight PWM.

### 1. Home  (`screenshots/01-home.png`)

- **Purpose:** at-a-glance health of everything; jump into any source; triage alerts.
- **Layout:** header, then a flex row (`gap:10px`, padding 11px):
  - **Left (flex:1):** 2×2 CSS grid of **source tiles** (`grid-auto-rows:1fr`, gap 10px).
  - **Right (fixed 220px):** **Alerts panel** (`#0E141B`).
- **Source tile** (`#161C24`, border `#202834`, radius 14, padding 14×15, tap →
  source page, active state border `#3A4552`):
  - Top row: status dot (9px, status color) + source name (19px/600, text).
  - Big number (30–34px/700, text) — headline metric.
  - Label (13px muted).
  - Sparkline: flex row of bars, `height:28px`, each bar `flex:1`, `background:currentColor`
    (tile sets `color` to the source hue), `opacity:.5`, radius 1px.
  - Sub caption (12px faint).
  - Tile headline data:
    - **Anthropic:** big = peak 5h-window % across shown accounts (e.g. `88%`); label
      `<Account> · peak 5h window`; sub `3 Max accounts`; status amber if peak ≥ usage
      threshold else good; hue terracotta `#D08770`.
    - **Cloudflare:** big = total requests today (`4.28M`); label `requests today`; sub
      `12 sites · 1 down` (or `· all up`); status red if any down, amber if degraded,
      else good; hue blue.
    - **Paddle:** big = revenue today (`$1,248`); label `revenue today`; sub
      `4 apps · +12% MoM`; status good; hue green.
    - **GitHub:** big = total open issues (`96 open`); label `issues across repos`; sub
      `6 repos`; status good; hue amber.
- **Alerts panel:** header row `ALERTS` (12px, letter-spacing .12em, faint) + count
  badge (pill, text `#0B0F14` on badge color = worst level). Scrollable list of alert
  cards (`#161C24`, 3px left border in level color, radius 8, tap → the relevant source
  page): level tag (11px/700, level color) + relative time (faint) / message (13px text)
  / source (11px muted).
- **Alerts are derived** from live data + thresholds (see State):
  - any shown site `down` → CRITICAL
  - any shown site `degraded` (if 4xx alerts on) → WARNING
  - any shown account 5h usage ≥ threshold → WARNING
  - `cf-worker-kit` new issues → INFO
  - Sorted critical → warning → info.

### 2. Anthropic  (`screenshots/02-anthropic.png`)

- **Purpose:** monitor Claude usage across 3 Max subscription accounts.
- **Layout:** header (subtitle `3 Claude Max accounts`), then column (gap 10, padding 11):
  - Row of **3 account cards** (flex:1 each).
  - Full-width **Activity** panel (`#0E141B`), fixed height.
- **Account card** (`#161C24`, radius 14, padding 14):
  - Top: account name (19px/600) + plan chip (`Max 5×` / `Max 20×`, 11px/600 accent on
    `rgba(208,135,112,.14)`, radius 6).
  - Big usage: `<n>%` (34px/700, colored by severity: ≥ threshold amber, ≥60 amber-ish,
    else good) + `of 5h window` (13px muted).
  - **5h progress bar:** track `#2A3441` (8px, radius 5), fill = usage %, fill color =
    severity color.
  - **Week** row: label + `<n>%` (12px), thin bar (5px) filled to week %, fill blue
    `#6AA0D8`.
  - Footer (top border `#202834`): `RESETS IN <h>h <mm>m` (16px/600) | `MESSAGES <n>`
    (16px/600, right aligned). Reset counts **down live**.
  - Example data: Personal · Max 5× · 46% · wk 61% · resets 2h13m · 128 msgs;
    Work · Max 20× · 88% (warn) · wk 74% · 1h02m · 412; Studio · Max 20× · 22% · wk 39%
    · 3h48m · 95.
- **Activity panel:** header `ACTIVITY · messages / hour` (13px muted) + `Today <total>`.
  24-bar histogram (height 56px, bars `currentColor` = accent, opacity .75, radius 2).
  Axis row: `00 06 12 18 24` (11px faint).

### 3. Cloudflare  (`screenshots/03-cloudflare.png`)

- **Purpose:** combined analytics + per-site health for 12 sites, paginated 6/page.
- **Layout:** header (subtitle `12 sites · combined analytics`), then:
  - **Totals strip:** 4-column grid of stat tiles — `Requests · today 4.28M`,
    `Bandwidth 312 GB`, `Threats blocked 18.4K` (amber value), `Cache hit ratio 94.2%`
    (green value). Each: label 12px muted + value 24px/700.
  - **Sites panel** (`#0E141B`): header row `SITES` + `<n> shown · <live> req/min` (the
    req/min figure wobbles live) on the left; **pager** on the right — `‹` button
    (34×34), `1 / 2` label, `›` button. Buttons are ≥34px (bump to 44px min in firmware).
  - **Site rows** (6 per page, height 56px, bottom divider `#161C24`), CSS grid
    `14px 1fr 86px 70px 74px 96px`, align center:
    status dot (10px) | domain (16px text, ellipsis) | requests (15px text, right) |
    bandwidth (14px muted, right) | mini sparkline (height 24px, `currentColor` = status
    color) | status text (13px/600, status color).
  - 12 sites total; `blog.wizemann.com` = degraded, `legacy.wizemann.com` = offline
    (req `—`). All others operational.

### 4. Paddle  (`screenshots/04-paddle.png`)

- **Purpose:** sales overview for 4 macOS products.
- **Layout:** header (subtitle `4 macOS products`), then:
  - **Totals strip:** 3-column grid — `Revenue · today $1,248` (green), `Revenue · month
    $98,720`, and a combined tile `<sales> sales · <customers> customers` / `+12% MoM`
    (green).
  - **Product grid:** 2×2 (`grid-auto-rows:1fr`, gap 10). Each product card
    (`#161C24`, radius 14, padding 14, `color` = green for sparkline):
    - Name (19px/600) + sub (`macOS · <category>`, 12px faint).
    - Three mini-stats row (gap 18): `PURCHASES` / `CUSTOMERS` / `REVENUE` — each a
      11px faint label over a 17px value; revenue value is green/700.
    - Sparkline (height 26px, `currentColor` green, opacity .55).
  - Products: PixelPeek (1,284 / 4,102 / $38,540), CleanShot Pro (892 / 2,740 /
    $26,180), FocusBar (2,410 / 6,980 / $19,280), SnapVault (512 / 1,190 / $14,720).

### 5. GitHub  (`screenshots/05-github.png`)

- **Purpose:** repo health for 6 repositories.
- **Layout:** header (subtitle `6 repositories`), then:
  - **Summary strip:** 3-column grid — `Repositories 6`, `Open issues 96` (amber),
    `Open PRs 18` (blue). Label 12px muted + value 22px/700.
  - **Repo list** (`#0E141B`, scrollable). Each row (height 57px, bottom divider), CSS
    grid `1fr 66px 78px 62px 58px`, align center:
    - Left cell: language dot (10px, language color) + repo name (16px text) over
      `<owner> · <lang>` (11px faint).
    - `★ <stars>` (14px amber, right) | `<n> issues` (14px text, right) | `<n> PR`
      (14px blue, right) | `<ago>` (13px faint, right).
  - Repos: claudemon (★342, 12 issues, 3 PR, C++, 2h), pixelpeek (★1.2k, 28, 5, Swift,
    4h), focusbar (★864, 9, 1, Swift, 1d), cf-worker-kit (★2.4k, 41, 8, TypeScript, 6h),
    paddle-sync (★156, 4, 0, Go, 3d), desk-dash (★78, 2, 1, Rust, 5h).
  - Language dot colors: C++ `#8FBF7F`, Swift `#E0B25A`, TypeScript/Go `#6AA0D8`,
    Rust `#D08770`.

### 6–9. Web Admin  (`screenshots/06..09-admin-*.png`)

Rendered as a **browser window** (title bar with traffic-light dots + URL pill
`claudemon.local/admin`). Layout: left **sidebar** (206px, `#0E141B`, right border) with
brand `ClaudeMon` (18px/700 accent) + `Admin console` caption + 4 nav items; **main
panel** scrolls. Nav item: 3px active bar (accent) + label; active item bg `#161C24`,
active label accent, inactive muted.

- **Sources** (`06`): heading `Data sources` + description. One card per source
  (`#0E141B`, radius 12): name (17px/600) + connection pill (`Connected` green /
  `Disconnected` red, on tinted bg) + a **connect toggle** (44×26 pill switch, on =
  accent, knob 22px white, slides 2px→20px). Below: `API TOKEN` label + masked text
  input (mono 13px, `#161C24`, editable) + `Save` button (accent bg, `#0B0F14` text).
  Sources: Anthropic (connected), Cloudflare (connected), Paddle (connected), GitHub
  (disconnected).
- **Displays** (`07`): heading + two columns.
  - Left `PAGES · ORDER`: one row per page — up/down reorder arrows (stacked 26×20
    buttons) + page name + enable toggle. Selecting a row highlights it (border accent)
    and loads its items on the right.
  - Right `<Page> · items shown`: checkbox list of that source's items (checkbox 20px,
    checked = accent fill + `#0B0F14` ✓, unchecked = 1.5px `#3A4552` border). Toggling
    hides/shows the item on the device.
- **Alerts** (`08`): heading + cards — **Claude usage threshold** (slider 50–100,
  value shown in accent, drives the account-usage warnings), **Alert when a site goes
  offline** (toggle), **Alert on 4xx/5xx spikes** (toggle).
- **Device** (`09`): **Brightness** slider (15–100, live-dims the panel), **Refresh
  interval** slider (15–300s, step 15), plus static info tiles `THEME Dark · locked` and
  `TIMEZONE Europe / Zurich`.

---

## Interactions & Behavior

- **Navigation:** tap a home tile → its source page. Header `‹` → home. Cloudflare
  pager `‹`/`›` steps site pages (clamped 0..last). Top segmented control switches
  Device ⇄ Web Admin. Admin sidebar switches tabs. All transitions **instant** (no
  slide/fade) per hardware constraint.
- **Feedback:** tappables use an active state (border lighten to `#3A4552` on tiles,
  opacity .6–.8 on buttons) — instant, not animated.
- **Live behavior:**
  - Clock ticks every 1s (`HH:MM`, 24h). Date shows `Ddd D Mon`.
  - Account **reset countdowns** tick down each second from fixed reset offsets, wrapping
    modulo the window length.
  - A slow "pulse" every 4s nudges live figures (e.g. Cloudflare `req/min`). Gate all
    live updates behind a **live/paused** flag.
- **Admin → device coupling (important):**
  - Page enable toggle removes the tile from Home *and* blocks the page.
  - Page reorder changes Home tile order.
  - Item checkboxes filter the lists on each source page (and the counts/alerts derived
    from them).
  - Source connect toggle reflects connection state.
  - Brightness sets the dim overlay / backlight.
  - Usage threshold + the two alert toggles change which alerts are generated.

## State Management

Prototype state (recreate equivalently in firmware — a config struct persisted to
flash/NVS, plus live-polled data):

- `screen` — `home | anthropic | cloudflare | paddle | github` (device view).
- `view` — `device | admin`.
- `cfPage` — Cloudflare pagination index.
- `adminTab` — `sources | displays | alerts | device`; `adminPageSel` — selected page
  in Displays.
- `now` (1s tick), `pulse` (4s tick) — drive clock, countdowns, live figures.
- **Config (persisted):**
  - `pages[]` — ordered list `{key,name}` (order = Home tile order).
  - `enabled{}` — per-page on/off.
  - `sources[]` — `{key,name,token,connected}`.
  - `shown{}` — per-source boolean array (which items appear).
  - `settings{}` — `brightness`, `refresh`, `usageAlert`, `alertDown`, `alert4xx`.
- **Data (polled from APIs):** the anthropic/cloudflare/paddle/github objects — see the
  literal example values in each screen section and in the prototype's `this.base`.

## Data sources & fetching (real implementation)

Each source needs a token entered in Admin, then polled every `refresh` seconds:

- **Anthropic:** usage/limits per account (3 Max subscriptions) — 5h-window %, weekly %,
  reset time, message counts, hourly activity.
- **Cloudflare:** GraphQL Analytics per zone — requests, bandwidth, threats, cache-hit,
  and origin health/status for 12 zones; plus combined totals.
- **Paddle:** transactions/subscriptions per product — purchase count, customer count,
  revenue (today + month).
- **GitHub:** repo metadata for 6 repos — stars, open issues, open PRs, primary language,
  last push time.

Store tokens encrypted (device spec calls for encrypted-at-rest on the panel).

## Assets

- **No image/icon assets.** All glyphs are text/unicode: `‹` `›` back/pager, `★` stars,
  `✓` checkbox, `🔒`/traffic-lights in the admin browser chrome (decorative — replace or
  drop in firmware). Status is conveyed by colored dots (flat CSS circles).
- **Font:** Montserrat (Google Fonts in the prototype). In firmware, embed Montserrat as
  an LVGL font at 14/16/20/28.
- No SVG illustrations; nothing to export.

## Files

- `ClaudeMon Cockpit.dc.html` — the interactive prototype (opens in a browser). Contains
  every screen, all data, and the admin. This is the source of truth for layout/behavior.
- `support.js` — runtime required to open the prototype `.dc.html` in a browser.
- `screenshots/01..09-*.png` — reference captures of each screen at hi-res.
- (Reference) original *ClaudeMon Display — Design Spec* — the hardware/design-system
  spec this was built against (in the project `uploads/`).

## Suggested build order

1. LVGL scaffold: 800×480, dark theme, Montserrat fonts at 4 sizes, palette as LVGL
   styles/constants (tokens above).
2. Chrome: header (both variants) + back nav + segmented device/admin (admin can be a
   separate served page).
3. Home grid + tile widget + alerts panel (with derived-alert logic).
4. The four source pages (reuse a card + sparkline + list-row widget set).
5. Live loop: clock, countdowns, poll-and-refresh, live/paused.
6. Web Admin page + config persistence (NVS) + wire settings back into the device.
