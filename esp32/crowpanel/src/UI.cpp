#include "UI.h"
#include <lvgl.h>
#include <Arduino.h>

// ----------------------------------------------------------------- palette
// Exact hex from the design handoff (design/design_handoff_claudemon_cockpit).
#define COL_BG       lv_color_hex(0x0b0f14)   // screen background
#define COL_TILE     lv_color_hex(0x161c24)   // cards / tiles / buttons
#define COL_SUNK     lv_color_hex(0x0e141b)   // recessed panels (alerts, lists, wells)
#define COL_BORDER   lv_color_hex(0x202834)   // 1px borders around tiles
#define COL_DIV      lv_color_hex(0x161c24)   // row separators inside lists
#define COL_TEXT     lv_color_hex(0xe6edf3)   // primary text, values
#define COL_MUTED    lv_color_hex(0x8b98a5)   // secondary text, labels
#define COL_FAINT    lv_color_hex(0x6b7885)   // captions, timestamps, axes
#define COL_TRACK    lv_color_hex(0x2a3441)   // progress-bar tracks
#define COL_ACTIVE   lv_color_hex(0x3a4552)   // tappable active-state border

#define COL_ACCENT   lv_color_hex(0xd08770)   // brand / back / Anthropic hue
#define COL_GOOD     lv_color_hex(0x8fbf7f)   // healthy / positive / Paddle hue
#define COL_BLUE     lv_color_hex(0x6aa0d8)   // info / weekly bar / PRs / Cloudflare hue
#define COL_AMBER    lv_color_hex(0xe0b25a)   // warnings / threats / stars / GitHub hue
#define COL_CRIT     lv_color_hex(0xbf616a)   // offline / critical

// Type scale — the four enabled Montserrat sizes (see lv_conf.h).
#define F14  &lv_font_montserrat_14
#define F16  &lv_font_montserrat_16
#define F20  &lv_font_montserrat_20
#define F28  &lv_font_montserrat_28

static const int SITES_PER_PAGE = 6;

// The five device screens. Home is the grid; the rest are source pages.
enum Screen { SC_HOME, SC_ANTHROPIC, SC_CLOUDFLARE, SC_PADDLE, SC_GITHUB, SC_COUNT };
static const char* kTitle[SC_COUNT]    = { "CLAUDEMON", "Anthropic", "Cloudflare", "Paddle", "GitHub" };
static const char* kSubtitle[SC_COUNT] = { "", "3 Claude Max accounts", "combined analytics",
                                           "4 macOS products", "6 repositories" };

// ----------------------------------------------------------------- state
static lv_obj_t* s_screen[SC_COUNT] = {nullptr};  // one full-size container each
static lv_obj_t* s_hdrHome = nullptr;             // home-variant header
static lv_obj_t* s_hdrPage = nullptr;             // page-variant header

// Home header widgets.
static lv_obj_t* s_homeClock = nullptr;
static lv_obj_t* s_homeDate  = nullptr;
static lv_obj_t* s_pill      = nullptr;           // status pill container
static lv_obj_t* s_pillDot   = nullptr;
static lv_obj_t* s_pillTxt   = nullptr;
static lv_obj_t* s_wifiHome  = nullptr;           // WiFi icon (shown when associated)

// Page header widgets.
static lv_obj_t* s_pageTitle = nullptr;
static lv_obj_t* s_pageSub   = nullptr;
static lv_obj_t* s_liveDot   = nullptr;
static lv_obj_t* s_liveTxt   = nullptr;
static lv_obj_t* s_pageClock = nullptr;
static lv_obj_t* s_wifiPage  = nullptr;
static int       s_wifiState = -1;                // -1 unknown, 0 down, 1 up

static lv_obj_t* s_stale     = nullptr;           // STALE banner overlay
static lv_obj_t* s_dim       = nullptr;           // brightness dim overlay

// Live-tick handles: labels the 1 Hz timer mutates in place (no rebuild).
static lv_obj_t* s_resetLbl[MAX_ACCOUNTS] = {nullptr};  // per-account RESETS-IN value

static Dashboard s_data;                          // last payload (for repaints/nav)
static bool      s_haveData = false;
static int       s_active   = SC_HOME;
static int       s_cfPage   = 0;
static bool      s_live     = true;
static int32_t   s_clock    = -1;                 // ticking seconds-since-midnight
static int32_t   s_fhSec[MAX_ACCOUNTS] = {-1,-1,-1};  // ticking seconds-to-reset
static bool      s_dirty[SC_COUNT] = {true, true, true, true, true};  // per-screen: not currently built

// ----------------------------------------------------------------- helpers

static lv_color_t statusColor(char st) {
    switch (st) {
        case 'o': return COL_GOOD;   // up / ok
        case 'g': return COL_AMBER;  // degraded
        case 'x': return COL_CRIT;   // down
        case 'a': return COL_AMBER;  // auth
        case 'e': return COL_CRIT;   // err
        case 'd': return COL_AMBER;  // drift
        default:  return COL_GOOD;
    }
}

static const char* statusText(char st) {
    switch (st) {
        case 'o': return "Operational";
        case 'g': return "Degraded";
        case 'x': return "Offline";
        case 'a': return "Auth";
        case 'e': return "Error";
        default:  return "Operational";
    }
}

static lv_color_t levelColor(int8_t lvl) {
    switch (lvl) { case 0: return COL_CRIT; case 1: return COL_AMBER; default: return COL_BLUE; }
}

// Severity color for the account usage headline / bars.
static lv_color_t usageColor(int8_t pct) {
    if (pct < 0)  return COL_MUTED;
    if (pct >= 80) return COL_AMBER;
    if (pct >= 60) return COL_AMBER;
    return COL_GOOD;
}

static void fmtClock(int32_t secs, char* buf, size_t n) {
    if (secs < 0) { snprintf(buf, n, "--:--"); return; }
    secs %= 86400;
    snprintf(buf, n, "%02d:%02d", (int)(secs / 3600), (int)((secs / 60) % 60));
}

// "2h 10m" / "0h 59m" from raw seconds; "--" when unknown.
static void fmtResetsIn(int32_t secs, char* buf, size_t n) {
    if (secs < 0) { snprintf(buf, n, "--"); return; }
    int h = secs / 3600, m = (secs / 60) % 60;
    snprintf(buf, n, "%dh %02dm", h, m);
}

// ----------------------------------------------------------------- small builders

static lv_obj_t* flexBox(lv_obj_t* parent, lv_flex_flow_t flow, lv_coord_t gap) {
    lv_obj_t* c = lv_obj_create(parent);
    lv_obj_set_style_bg_opa(c, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(c, 0, 0);
    lv_obj_set_style_pad_all(c, 0, 0);
    lv_obj_set_flex_flow(c, flow);
    lv_obj_set_style_pad_row(c, gap, 0);
    lv_obj_set_style_pad_column(c, gap, 0);
    lv_obj_clear_flag(c, LV_OBJ_FLAG_SCROLLABLE);
    return c;
}

static lv_obj_t* line(lv_obj_t* parent, const char* text, lv_color_t color,
                      const lv_font_t* font = F16) {
    lv_obj_t* l = lv_label_create(parent);
    lv_label_set_text(l, text ? text : "");
    lv_obj_set_style_text_color(l, color, 0);
    lv_obj_set_style_text_font(l, font, 0);
    return l;
}

// A rounded status dot.
static lv_obj_t* dot(lv_obj_t* parent, lv_color_t color, int size = 9) {
    lv_obj_t* d = lv_obj_create(parent);
    lv_obj_set_size(d, size, size);
    lv_obj_set_style_radius(d, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(d, color, 0);
    lv_obj_set_style_bg_opa(d, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(d, 0, 0);
    lv_obj_set_style_pad_all(d, 0, 0);
    lv_obj_clear_flag(d, LV_OBJ_FLAG_SCROLLABLE);
    return d;
}

// A rounded card (tile) — flat fill, 1px border, radius 14.
static lv_obj_t* card(lv_obj_t* parent, int radius = 14) {
    lv_obj_t* c = lv_obj_create(parent);
    lv_obj_set_style_bg_color(c, COL_TILE, 0);
    lv_obj_set_style_bg_opa(c, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(c, COL_BORDER, 0);
    lv_obj_set_style_border_width(c, 1, 0);
    lv_obj_set_style_radius(c, radius, 0);
    lv_obj_set_style_pad_all(c, 14, 0);
    lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(c, 6, 0);
    lv_obj_clear_flag(c, LV_OBJ_FLAG_SCROLLABLE);
    return c;
}

// A sunken well (recessed panel: alerts panel, lists, stat wells).
static lv_obj_t* well(lv_obj_t* parent, int radius = 12) {
    lv_obj_t* c = lv_obj_create(parent);
    lv_obj_set_style_bg_color(c, COL_SUNK, 0);
    lv_obj_set_style_bg_opa(c, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(c, COL_BORDER, 0);
    lv_obj_set_style_border_width(c, 1, 0);
    lv_obj_set_style_radius(c, radius, 0);
    lv_obj_set_style_pad_all(c, 12, 0);
    lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(c, 8, 0);
    lv_obj_clear_flag(c, LV_OBJ_FLAG_SCROLLABLE);
    return c;
}

// An uppercase micro-label (letter-spaced, faint).
static lv_obj_t* microLabel(lv_obj_t* parent, const char* text, lv_color_t color = COL_FAINT) {
    lv_obj_t* l = line(parent, text, color, F14);
    lv_obj_set_style_text_letter_space(l, 1, 0);
    return l;
}

// A stat tile for the totals/summary strips: micro-label over a big value.
static lv_obj_t* statTile(lv_obj_t* parent, const char* cap, const char* val,
                          lv_color_t vcol, const lv_font_t* vfont = F20) {
    lv_obj_t* t = well(parent, 12);
    lv_obj_set_style_pad_all(t, 12, 0);
    lv_obj_set_style_pad_row(t, 4, 0);
    lv_obj_set_flex_grow(t, 1);
    microLabel(t, cap, COL_MUTED);
    line(t, val && val[0] ? val : "--", vcol, vfont);
    return t;
}

// A thin progress bar over a track.
static lv_obj_t* progressBar(lv_obj_t* parent, int8_t pct, lv_color_t fill, int h = 8) {
    lv_obj_t* bar = lv_bar_create(parent);
    lv_obj_set_size(bar, lv_pct(100), h);
    lv_bar_set_range(bar, 0, 100);
    lv_bar_set_value(bar, pct < 0 ? 0 : pct, LV_ANIM_OFF);
    lv_obj_set_style_radius(bar, 5, LV_PART_MAIN);
    lv_obj_set_style_radius(bar, 5, LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(bar, COL_TRACK, LV_PART_MAIN);
    lv_obj_set_style_bg_color(bar, fill, LV_PART_INDICATOR);
    return bar;
}

// A tile-set-color sparkline: a row of flat bars, each flex-grown, opacity .5.
// Reads clean on the RGB565 panel (no gradient banding).
static void sparkline(lv_obj_t* parent, const std::vector<uint8_t>& pts,
                      lv_color_t color, int height = 28, lv_opa_t opa = LV_OPA_50) {
    lv_obj_t* row = flexBox(parent, LV_FLEX_FLOW_ROW, 2);
    lv_obj_set_size(row, lv_pct(100), height);
    lv_obj_set_flex_align(row, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_END);
    if (pts.size() < 2) return;
    for (uint8_t v : pts) {
        lv_obj_t* b = lv_obj_create(row);
        lv_obj_set_flex_grow(b, 1);
        int bh = (int)(height * (v < 4 ? 4 : v) / 100);
        if (bh < 2) bh = 2;
        lv_obj_set_height(b, bh);
        lv_obj_set_style_bg_color(b, color, 0);
        lv_obj_set_style_bg_opa(b, opa, 0);
        lv_obj_set_style_border_width(b, 0, 0);
        lv_obj_set_style_radius(b, 1, 0);
        lv_obj_set_style_pad_all(b, 0, 0);
        lv_obj_clear_flag(b, LV_OBJ_FLAG_SCROLLABLE);
    }
}


// A subscription/plan chip: accent text on a tinted pill.
static void chip(lv_obj_t* parent, const char* text, lv_color_t txt, lv_color_t bg) {
    lv_obj_t* c = lv_obj_create(parent);
    lv_obj_set_size(c, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_set_style_bg_color(c, bg, 0);
    lv_obj_set_style_bg_opa(c, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(c, 0, 0);
    lv_obj_set_style_radius(c, 6, 0);
    lv_obj_set_style_pad_hor(c, 8, 0);
    lv_obj_set_style_pad_ver(c, 3, 0);
    lv_obj_clear_flag(c, LV_OBJ_FLAG_SCROLLABLE);
    line(c, text, txt, F14);
}

// A right-aligned label helper used inside grid/rows.
static lv_obj_t* rlabel(lv_obj_t* parent, const char* text, lv_color_t col,
                        const lv_font_t* font = F14) {
    lv_obj_t* l = line(parent, text, col, font);
    lv_obj_set_style_text_align(l, LV_TEXT_ALIGN_RIGHT, 0);
    return l;
}

// ----------------------------------------------------------------- navigation

static void applyChrome();
static void fillHome();
static void fillAnthropic();
static void fillCloudflare();
static void fillPaddle();
static void fillGithub();

static void buildScreen(int s) {
    switch (s) {
        case SC_HOME:       fillHome();       break;
        case SC_ANTHROPIC:  fillAnthropic();  break;
        case SC_CLOUDFLARE: fillCloudflare(); break;
        case SC_PADDLE:     fillPaddle();     break;
        case SC_GITHUB:     fillGithub();     break;
        default: break;
    }
}

// Only ONE screen's object tree lives at a time. Building all five fully-
// populated screens in a single ui_update() exhausts LVGL's heap and crashes in
// lv_label_create (null deref, seen on the demo payload). So we free every
// non-active screen and (re)build the target lazily on navigation — peak object
// count stays ~one screen, which also cuts rebuild time and jitter.
static void showScreen(int s) {
    if (s < 0) s = 0;
    if (s >= SC_COUNT) s = SC_COUNT - 1;

    for (int k = 0; k < SC_COUNT; k++) {
        if (k != s && !s_dirty[k]) {
            // Anthropic's reset labels are live-tick handles into this tree —
            // null them before freeing so the 1 Hz timer can't touch dead memory.
            if (k == SC_ANTHROPIC)
                for (size_t i = 0; i < MAX_ACCOUNTS; i++) s_resetLbl[i] = nullptr;
            lv_obj_clean(s_screen[k]);
            s_dirty[k] = true;
        }
    }

    s_active = s;
    if (s_haveData && s_dirty[s]) { buildScreen(s); s_dirty[s] = false; }

    for (int k = 0; k < SC_COUNT; k++) {
        if (k == s) lv_obj_clear_flag(s_screen[k], LV_OBJ_FLAG_HIDDEN);
        else        lv_obj_add_flag(s_screen[k], LV_OBJ_FLAG_HIDDEN);
    }
    applyChrome();
}

static void onTileClick(lv_event_t* e) {
    showScreen((int)(intptr_t)lv_event_get_user_data(e));
}

static void onBack(lv_event_t*) { showScreen(SC_HOME); }

// An alert card taps through to its originating source page.
static int alertTarget(const String& src) {
    if (src == "Cloudflare") return SC_CLOUDFLARE;
    if (src == "Anthropic")  return SC_ANTHROPIC;
    if (src == "GitHub")     return SC_GITHUB;
    if (src == "Paddle")     return SC_PADDLE;
    return SC_HOME;
}

static void onAlertClick(lv_event_t* e) {
    showScreen((int)(intptr_t)lv_event_get_user_data(e));
}

static void rebuildCloudflare();  // fwd: pager repaints only the CF page

static void onPagerPrev(lv_event_t*) {
    if (s_cfPage > 0) { s_cfPage--; rebuildCloudflare(); }
}
static void onPagerNext(lv_event_t*) {
    int last = ((int)s_data.sites.size() - 1) / SITES_PER_PAGE;
    if (last < 0) last = 0;
    if (s_cfPage < last) { s_cfPage++; rebuildCloudflare(); }
}

// ----------------------------------------------------------------- chrome

// A small WiFi "signal bars" icon (3 ascending bars), drawn from rectangles so
// it renders regardless of whether the font carries the FontAwesome symbols
// (ours doesn't — LV_SYMBOL_WIFI came out blank). The box is a FIXED size with
// absolutely-positioned bars: a SIZE_CONTENT box collapses to zero inside the
// header's nested SIZE_CONTENT flex row (the same trap that hid the clock).
// The caller pins it as a FLOATING, absolutely-aligned overlay so it sidesteps
// the header's flex cluster entirely (SIZE_CONTENT children there collapse to
// zero — that's what hid both this and the status pill). ui_set_wifi shows/hides
// it with the HIDDEN flag; being floating, that never triggers a flex relayout.
static lv_obj_t* wifiBars(lv_obj_t* parent, lv_color_t color) {
    lv_obj_t* box = lv_obj_create(parent);
    lv_obj_set_size(box, 15, 14);
    lv_obj_set_style_bg_opa(box, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(box, 0, 0);
    lv_obj_set_style_pad_all(box, 0, 0);
    lv_obj_clear_flag(box, LV_OBJ_FLAG_SCROLLABLE);
    const int hs[3] = {5, 9, 13};
    for (int i = 0; i < 3; i++) {
        lv_obj_t* bar = lv_obj_create(box);
        lv_obj_set_size(bar, 3, hs[i]);
        lv_obj_set_style_bg_color(bar, color, 0);
        lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(bar, 0, 0);
        lv_obj_set_style_radius(bar, 1, 0);
        lv_obj_set_style_pad_all(bar, 0, 0);
        lv_obj_clear_flag(bar, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_align(bar, LV_ALIGN_BOTTOM_LEFT, i * 5, 0);   // 3px bar + 2px gap
    }
    return box;
}

// Build both header variants (home + page) once; applyChrome() shows one.
static void buildHeaders(lv_obj_t* scr) {
    // --- Home variant ---
    s_hdrHome = flexBox(scr, LV_FLEX_FLOW_ROW, 0);
    lv_obj_set_size(s_hdrHome, lv_pct(100), 52);
    lv_obj_set_style_pad_hor(s_hdrHome, 11, 0);
    lv_obj_set_flex_align(s_hdrHome, LV_FLEX_ALIGN_SPACE_BETWEEN,
                          LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_border_color(s_hdrHome, COL_DIV, 0);
    lv_obj_set_style_border_side(s_hdrHome, LV_BORDER_SIDE_BOTTOM, 0);
    lv_obj_set_style_border_width(s_hdrHome, 1, 0);

    lv_obj_t* wordmark = line(s_hdrHome, "CLAUDEMON", COL_ACCENT, F28);
    (void)wordmark;

    lv_obj_t* right = flexBox(s_hdrHome, LV_FLEX_FLOW_ROW, 14);
    lv_obj_set_flex_align(right, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_size(right, LV_SIZE_CONTENT, LV_SIZE_CONTENT);

    // WiFi icon — a FLOATING overlay pinned just left of the clock (absolute, so
    // the header's flex cluster can't collapse it). Hidden until associated.
    s_wifiHome = wifiBars(s_hdrHome, COL_GOOD);
    lv_obj_add_flag(s_wifiHome, LV_OBJ_FLAG_FLOATING);
    lv_obj_align(s_wifiHome, LV_ALIGN_TOP_RIGHT, -112, 19);
    lv_obj_add_flag(s_wifiHome, LV_OBJ_FLAG_HIDDEN);

    // Status pill (dot + text on a tile pill).
    s_pill = flexBox(right, LV_FLEX_FLOW_ROW, 6);
    lv_obj_set_size(s_pill, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_set_flex_align(s_pill, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_bg_color(s_pill, COL_TILE, 0);
    lv_obj_set_style_bg_opa(s_pill, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(s_pill, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_pad_hor(s_pill, 12, 0);
    lv_obj_set_style_pad_ver(s_pill, 6, 0);
    s_pillDot = dot(s_pill, COL_GOOD, 7);
    s_pillTxt = line(s_pill, "all clear", COL_TEXT, F14);
    // Keep the pill text on one line — inside a SIZE_CONTENT flex the default
    // WRAP mode could break "1 critical" across two lines and clip it to "ical".
    lv_label_set_long_mode(s_pillTxt, LV_LABEL_LONG_CLIP);

    // Fixed-size clock column: a fixed HEIGHT (not SIZE_CONTENT) so the clock+
    // date stack can't overflow and clip. SIZE_CONTENT under-computed here (the
    // date label starts empty at build), and END-packing then pushed the clock
    // out the top of the header, clipping it to a sliver. A fixed 46px box with
    // the pair vertically centered leaves margin above and below both lines.
    lv_obj_t* clockcol = flexBox(right, LV_FLEX_FLOW_COLUMN, 0);
    lv_obj_set_size(clockcol, 96, 46);
    lv_obj_set_flex_align(clockcol, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_END);
    s_homeClock = line(clockcol, "--:--", COL_TEXT, F16);
    s_homeDate  = line(clockcol, "", COL_FAINT, F14);
    lv_label_set_long_mode(s_homeClock, LV_LABEL_LONG_CLIP);
    lv_label_set_long_mode(s_homeDate, LV_LABEL_LONG_CLIP);

    // --- Page variant ---
    s_hdrPage = flexBox(scr, LV_FLEX_FLOW_ROW, 12);
    lv_obj_set_size(s_hdrPage, lv_pct(100), 52);
    lv_obj_set_style_pad_hor(s_hdrPage, 11, 0);
    lv_obj_set_flex_align(s_hdrPage, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_border_color(s_hdrPage, COL_DIV, 0);
    lv_obj_set_style_border_side(s_hdrPage, LV_BORDER_SIDE_BOTTOM, 0);
    lv_obj_set_style_border_width(s_hdrPage, 1, 0);
    // The whole top bar taps home. The 44px back glyph is a small target and the
    // GT911 is twitchy near the top edge, so tapping anywhere in the page header
    // (title, clock, empty space) returns to the grid — the back glyph is just
    // the visible affordance.
    lv_obj_add_flag(s_hdrPage, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(s_hdrPage, onBack, LV_EVENT_CLICKED, nullptr);

    // Back button (44x40 tile, accent glyph).
    lv_obj_t* back = lv_obj_create(s_hdrPage);
    lv_obj_set_size(back, 44, 40);
    lv_obj_set_style_bg_color(back, COL_TILE, 0);
    lv_obj_set_style_bg_opa(back, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(back, 0, 0);
    lv_obj_set_style_radius(back, 10, 0);
    lv_obj_set_style_pad_all(back, 0, 0);
    lv_obj_clear_flag(back, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(back, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(back, onBack, LV_EVENT_CLICKED, nullptr);
    lv_obj_t* glyph = line(back, "<", COL_ACCENT, F28);
    lv_obj_center(glyph);

    lv_obj_t* titlecol = flexBox(s_hdrPage, LV_FLEX_FLOW_COLUMN, 0);
    lv_obj_set_flex_grow(titlecol, 1);
    lv_obj_set_height(titlecol, LV_SIZE_CONTENT);
    s_pageTitle = line(titlecol, "Anthropic", COL_TEXT, F28);
    s_pageSub   = line(titlecol, "", COL_MUTED, F14);

    lv_obj_t* pright = flexBox(s_hdrPage, LV_FLEX_FLOW_ROW, 12);
    lv_obj_set_size(pright, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_set_flex_align(pright, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    // (Home header carries the WiFi icon; drill-in pages show the LIVE dot.)
    lv_obj_t* livebox = flexBox(pright, LV_FLEX_FLOW_ROW, 6);
    lv_obj_set_size(livebox, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_set_flex_align(livebox, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    s_liveDot = dot(livebox, COL_GOOD, 7);
    s_liveTxt = microLabel(livebox, "LIVE", COL_GOOD);
    s_pageClock = line(pright, "--:--", COL_TEXT, F20);

    lv_obj_add_flag(s_hdrPage, LV_OBJ_FLAG_HIDDEN);
}

// Show the right header for the active screen and sync its live-tick labels.
static void applyChrome() {
    bool home = (s_active == SC_HOME);
    if (home) {
        lv_obj_clear_flag(s_hdrHome, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_hdrPage, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_add_flag(s_hdrHome, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s_hdrPage, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(s_pageTitle, kTitle[s_active]);
        // Cloudflare's subtitle carries a live site count; others are static.
        if (s_active == SC_CLOUDFLARE) {
            char buf[48];
            snprintf(buf, sizeof(buf), "%d sites - combined analytics", (int)s_data.sites.size());
            lv_label_set_text(s_pageSub, buf);
        } else {
            lv_label_set_text(s_pageSub, kSubtitle[s_active]);
        }
        lv_label_set_text(s_liveTxt, s_live ? "LIVE" : "PAUSED");
        lv_obj_set_style_bg_color(s_liveDot, s_live ? COL_GOOD : COL_FAINT, 0);
        lv_obj_set_style_text_color(s_liveTxt, s_live ? COL_GOOD : COL_FAINT, 0);
    }
}

// Refresh the home status pill from the current alert set.
static void applyPill() {
    int worst = 3;   // 0 crit, 1 warn, 2 info, 3 none
    int crit = 0;
    for (const AlertRow& a : s_data.alerts) {
        if (a.lvl < worst) worst = a.lvl;
        if (a.lvl == 0) crit++;
    }
    lv_color_t col; char buf[24];
    if (worst == 0)      { col = COL_CRIT;  snprintf(buf, sizeof(buf), "%d critical", crit ? crit : 1); }
    else if (worst == 1) { col = COL_AMBER; snprintf(buf, sizeof(buf), "%d warning", (int)s_data.alerts.size()); }
    else if (worst == 2) { col = COL_BLUE;  snprintf(buf, sizeof(buf), "%d info", (int)s_data.alerts.size()); }
    else                 { col = COL_GOOD;  snprintf(buf, sizeof(buf), "all clear"); }
    lv_obj_set_style_bg_color(s_pillDot, col, 0);
    lv_label_set_text(s_pillTxt, buf);
}

// ----------------------------------------------------------------- home

// One source tile in the 2x2 grid.
static void homeTile(lv_obj_t* grid, int target, char st, const char* name,
                     lv_color_t hue, const char* big, const char* label,
                     const std::vector<uint8_t>& spark, const char* sub) {
    lv_obj_t* t = card(grid, 14);
    lv_obj_set_size(t, lv_pct(100), lv_pct(100));
    lv_obj_set_style_pad_row(t, 4, 0);
    lv_obj_add_flag(t, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(t, onTileClick, LV_EVENT_CLICKED, (void*)(intptr_t)target);
    lv_obj_set_style_border_color(t, COL_ACTIVE, LV_STATE_PRESSED);

    lv_obj_t* top = flexBox(t, LV_FLEX_FLOW_ROW, 8);
    lv_obj_set_size(top, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_align(top, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    dot(top, statusColor(st), 9);
    line(top, name, COL_TEXT, F20);

    line(t, big, COL_TEXT, F28);
    line(t, label, COL_MUTED, F14);

    lv_obj_t* spacer = flexBox(t, LV_FLEX_FLOW_COLUMN, 0);  // push spark to bottom
    lv_obj_set_flex_grow(spacer, 1);
    lv_obj_set_width(spacer, lv_pct(100));

    sparkline(t, spark, hue, 28, LV_OPA_50);
    line(t, sub, COL_FAINT, F14);
}

// The right-hand alerts panel.
static void alertsPanel(lv_obj_t* parent) {
    lv_obj_t* panel = well(parent, 14);
    lv_obj_set_size(panel, 220, lv_pct(100));
    lv_obj_set_style_pad_all(panel, 12, 0);
    lv_obj_set_style_pad_row(panel, 8, 0);

    lv_obj_t* hdr = flexBox(panel, LV_FLEX_FLOW_ROW, 0);
    lv_obj_set_size(hdr, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_align(hdr, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_t* h = microLabel(hdr, "ALERTS", COL_FAINT);
    lv_obj_set_style_text_letter_space(h, 2, 0);
    if (!s_data.alerts.empty()) {
        int worst = 3;
        for (const AlertRow& a : s_data.alerts) if (a.lvl < worst) worst = a.lvl;
        char cnt[8]; snprintf(cnt, sizeof(cnt), "%d", (int)s_data.alerts.size());
        chip(hdr, cnt, COL_BG, levelColor(worst));
    }

    lv_obj_t* list = flexBox(panel, LV_FLEX_FLOW_COLUMN, 8);
    lv_obj_set_size(list, lv_pct(100), lv_pct(100));
    lv_obj_set_flex_grow(list, 1);
    lv_obj_add_flag(list, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scroll_dir(list, LV_DIR_VER);
    lv_obj_set_style_pad_right(list, 2, 0);

    if (s_data.alerts.empty()) {
        lv_obj_t* empty = line(list, "No alerts", COL_FAINT, F14);
        lv_obj_set_style_pad_top(empty, 6, 0);
        return;
    }

    for (const AlertRow& a : s_data.alerts) {
        lv_color_t lc = levelColor(a.lvl);
        lv_obj_t* c = lv_obj_create(list);
        lv_obj_set_size(c, lv_pct(100), LV_SIZE_CONTENT);
        lv_obj_set_style_bg_color(c, COL_TILE, 0);
        lv_obj_set_style_bg_opa(c, LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(c, 0, 0);
        lv_obj_set_style_border_side(c, LV_BORDER_SIDE_LEFT, 0);
        lv_obj_set_style_border_color(c, lc, 0);
        lv_obj_set_style_border_width(c, 3, 0);
        lv_obj_set_style_radius(c, 8, 0);
        lv_obj_set_style_pad_all(c, 9, 0);
        lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
        lv_obj_set_style_pad_row(c, 2, 0);
        lv_obj_clear_flag(c, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_add_flag(c, LV_OBJ_FLAG_CLICKABLE);
        lv_obj_add_event_cb(c, onAlertClick, LV_EVENT_CLICKED,
                            (void*)(intptr_t)alertTarget(a.src));

        lv_obj_t* r = flexBox(c, LV_FLEX_FLOW_ROW, 0);
        lv_obj_set_size(r, lv_pct(100), LV_SIZE_CONTENT);
        lv_obj_set_flex_align(r, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);
        line(r, a.tag.c_str(), lc, F14);
        line(r, a.time.c_str(), COL_FAINT, F14);

        lv_obj_t* msg = line(c, a.msg.c_str(), COL_TEXT, F14);
        lv_obj_set_width(msg, lv_pct(100));
        lv_label_set_long_mode(msg, LV_LABEL_LONG_WRAP);
        line(c, a.src.c_str(), COL_MUTED, F14);
    }
}

static void fillHome() {
    lv_obj_t* page = s_screen[SC_HOME];
    lv_obj_clean(page);
    lv_obj_set_flex_flow(page, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_all(page, 11, 0);
    lv_obj_set_style_pad_column(page, 10, 0);

    // Left: 2x2 tile grid (flex:1).
    lv_obj_t* gridwrap = flexBox(page, LV_FLEX_FLOW_COLUMN, 10);
    lv_obj_set_flex_grow(gridwrap, 1);
    lv_obj_set_height(gridwrap, lv_pct(100));

    lv_obj_t* rowA = flexBox(gridwrap, LV_FLEX_FLOW_ROW, 10);
    lv_obj_set_width(rowA, lv_pct(100));
    lv_obj_set_flex_grow(rowA, 1);
    lv_obj_t* rowB = flexBox(gridwrap, LV_FLEX_FLOW_ROW, 10);
    lv_obj_set_width(rowB, lv_pct(100));
    lv_obj_set_flex_grow(rowB, 1);

    lv_obj_t* cellA[2], *cellB[2];
    for (int i = 0; i < 2; i++) {
        cellA[i] = flexBox(rowA, LV_FLEX_FLOW_COLUMN, 0);
        lv_obj_set_flex_grow(cellA[i], 1);
        lv_obj_set_height(cellA[i], lv_pct(100));
        cellB[i] = flexBox(rowB, LV_FLEX_FLOW_COLUMN, 0);
        lv_obj_set_flex_grow(cellB[i], 1);
        lv_obj_set_height(cellB[i], lv_pct(100));
    }

    // --- Anthropic tile: peak 5h %, warn if any >= threshold(80) ---
    {
        int peak = -1, peakIdx = 0;
        for (size_t i = 0; i < s_data.accounts.size(); i++)
            if (s_data.accounts[i].fhPct > peak) { peak = s_data.accounts[i].fhPct; peakIdx = i; }
        char big[16], label[48], sub[32];
        if (peak >= 0) snprintf(big, sizeof(big), "%d%%", peak);
        else           snprintf(big, sizeof(big), "--");
        const char* nm = s_data.accounts.empty() ? "" : s_data.accounts[peakIdx].label.c_str();
        snprintf(label, sizeof(label), "%s - peak 5h window", nm);
        snprintf(sub, sizeof(sub), "%d accounts", (int)s_data.accounts.size());
        char st = (peak >= 80) ? 'g' : 'o';
        // The usage endpoint has no per-account time series, so the Anthropic
        // tile carries no trend sparkline.
        const std::vector<uint8_t> spk;
        homeTile(cellA[0], SC_ANTHROPIC, st, "Anthropic", COL_ACCENT, big, label, spk, sub);
    }
    // --- Cloudflare tile: requests today, down/degraded sub ---
    {
        char sub[48];
        if (s_data.cfDown > 0)
            snprintf(sub, sizeof(sub), "%d sites - %d down", (int)s_data.sites.size(), s_data.cfDown);
        else if (s_data.cfDegraded > 0)
            snprintf(sub, sizeof(sub), "%d sites - %d degraded", (int)s_data.sites.size(), s_data.cfDegraded);
        else
            snprintf(sub, sizeof(sub), "%d sites - all up", (int)s_data.sites.size());
        char st = s_data.cfDown > 0 ? 'x' : (s_data.cfDegraded > 0 ? 'g' : 'o');
        // Use the first site's spark as the tile trend (host order = config order).
        const std::vector<uint8_t>& spk = s_data.sites.empty() ?
            std::vector<uint8_t>() : s_data.sites[0].spark;
        homeTile(cellA[1], SC_CLOUDFLARE, st, "Cloudflare", COL_BLUE,
                 s_data.cfTotals.req.length() ? s_data.cfTotals.req.c_str() : "--",
                 "requests today", spk, sub);
    }
    // --- Paddle tile: revenue today, MoM sub ---
    {
        char sub[48];
        snprintf(sub, sizeof(sub), "%d apps - %s MoM",
                 (int)s_data.products.size(),
                 s_data.paddleTotals.mom.length() ? s_data.paddleTotals.mom.c_str() : "0%");
        const std::vector<uint8_t>& spk = s_data.products.empty() ?
            std::vector<uint8_t>() : s_data.products[0].spark;
        homeTile(cellB[0], SC_PADDLE, 'o', "Paddle", COL_GOOD,
                 s_data.paddleTotals.revToday.length() ? s_data.paddleTotals.revToday.c_str() : "--",
                 "revenue today", spk, sub);
    }
    // --- GitHub tile: open issues, repo count sub ---
    {
        char big[24], sub[24];
        snprintf(big, sizeof(big), "%s open",
                 s_data.ghSummary.issues.length() ? s_data.ghSummary.issues.c_str() : "--");
        snprintf(sub, sizeof(sub), "%d repos", s_data.ghSummary.repos);
        // Synthesize a flat spark from repo issue presence (no per-repo series in payload).
        std::vector<uint8_t> spk;
        for (const RepoRow& r : s_data.repos) spk.push_back(r.issues.length() ? 70 : 20);
        homeTile(cellB[1], SC_GITHUB, 'o', "GitHub", COL_AMBER, big, "issues across repos", spk, sub);
    }

    alertsPanel(page);
    applyPill();
}

// ----------------------------------------------------------------- anthropic

static void fillAnthropic() {
    lv_obj_t* page = s_screen[SC_ANTHROPIC];
    lv_obj_clean(page);
    for (size_t i = 0; i < MAX_ACCOUNTS; i++) s_resetLbl[i] = nullptr;
    lv_obj_set_flex_flow(page, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(page, 11, 0);
    lv_obj_set_style_pad_row(page, 10, 0);

    if (s_data.accounts.empty()) {
        lv_obj_center(line(page, "NO CLAUDE ACCOUNTS", COL_MUTED));
        return;
    }

    // Row of account cards.
    lv_obj_t* row = flexBox(page, LV_FLEX_FLOW_ROW, 10);
    lv_obj_set_width(row, lv_pct(100));
    lv_obj_set_flex_grow(row, 1);

    for (size_t i = 0; i < s_data.accounts.size(); i++) {
        const AccountRow& a = s_data.accounts[i];
        lv_obj_t* c = card(row, 14);
        lv_obj_set_flex_grow(c, 1);
        lv_obj_set_height(c, lv_pct(100));
        lv_obj_set_style_pad_row(c, 8, 0);

        // Top: name + plan chip.
        lv_obj_t* top = flexBox(c, LV_FLEX_FLOW_ROW, 0);
        lv_obj_set_size(top, lv_pct(100), LV_SIZE_CONTENT);
        lv_obj_set_flex_align(top, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
        line(top, a.label.c_str(), COL_TEXT, F20);
        // Server-severity badge — only when the account is at warning or worse.
        if (a.sev.length()) {
            bool crit = (a.sev == "critical" || a.sev == "exceeded");
            chip(top, crit ? "CRITICAL" : "WARNING", crit ? COL_CRIT : COL_AMBER, COL_SUNK);
        }

        // Big usage % + caption.
        lv_obj_t* big = flexBox(c, LV_FLEX_FLOW_ROW, 6);
        lv_obj_set_size(big, lv_pct(100), LV_SIZE_CONTENT);
        lv_obj_set_flex_align(big, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_END);
        char pbuf[8];
        if (a.fhPct >= 0) snprintf(pbuf, sizeof(pbuf), "%d%%", a.fhPct);
        else              snprintf(pbuf, sizeof(pbuf), "--");
        line(big, pbuf, usageColor(a.fhPct), F28);
        // The currently-binding window's caption is accented (server is_active).
        line(big, "of 5h window", a.actv == "5h" ? COL_ACCENT : COL_MUTED, F14);

        progressBar(c, a.fhPct, usageColor(a.fhPct), 8);

        // Week row: label + pct, thin blue bar.
        lv_obj_t* wk = flexBox(c, LV_FLEX_FLOW_ROW, 0);
        lv_obj_set_size(wk, lv_pct(100), LV_SIZE_CONTENT);
        lv_obj_set_flex_align(wk, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
        line(wk, "Week", a.actv == "week" ? COL_ACCENT : COL_MUTED, F14);
        char wbuf[8];
        if (a.wkPct >= 0) snprintf(wbuf, sizeof(wbuf), "%d%%", a.wkPct);
        else              snprintf(wbuf, sizeof(wbuf), "--");
        line(wk, wbuf, COL_TEXT, F14);
        progressBar(c, a.wkPct, COL_BLUE, 5);

        // Scoped-weekly row — only when the account carries a scoped cap.
        if (a.wsPct >= 0) {
            lv_obj_t* ws = flexBox(c, LV_FLEX_FLOW_ROW, 0);
            lv_obj_set_size(ws, lv_pct(100), LV_SIZE_CONTENT);
            lv_obj_set_flex_align(ws, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
            line(ws, "Scoped", a.actv == "scoped" ? COL_ACCENT : COL_MUTED, F14);
            char sbuf[8]; snprintf(sbuf, sizeof(sbuf), "%d%%", a.wsPct);
            line(ws, sbuf, COL_TEXT, F14);
            progressBar(c, a.wsPct, COL_BLUE, 5);
        }

        // Extra-usage credits line — only when the account has credits enabled.
        if (a.cred.length()) {
            lv_obj_t* cr = flexBox(c, LV_FLEX_FLOW_ROW, 0);
            lv_obj_set_size(cr, lv_pct(100), LV_SIZE_CONTENT);
            lv_obj_set_flex_align(cr, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
            line(cr, "Credits", COL_MUTED, F14);
            line(cr, a.cred.c_str(), COL_GOOD, F14);
        }

        // Spacer, then footer.
        lv_obj_t* spacer = flexBox(c, LV_FLEX_FLOW_COLUMN, 0);
        lv_obj_set_flex_grow(spacer, 1);
        lv_obj_set_width(spacer, lv_pct(100));

        lv_obj_t* foot = lv_obj_create(c);
        lv_obj_set_size(foot, lv_pct(100), LV_SIZE_CONTENT);
        lv_obj_set_style_bg_opa(foot, LV_OPA_TRANSP, 0);
        lv_obj_set_style_border_color(foot, COL_BORDER, 0);
        lv_obj_set_style_border_side(foot, LV_BORDER_SIDE_TOP, 0);
        lv_obj_set_style_border_width(foot, 1, 0);
        lv_obj_set_style_pad_all(foot, 0, 0);
        lv_obj_set_style_pad_top(foot, 8, 0);
        lv_obj_set_flex_flow(foot, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(foot, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);
        lv_obj_clear_flag(foot, LV_OBJ_FLAG_SCROLLABLE);

        lv_obj_t* rin = flexBox(foot, LV_FLEX_FLOW_COLUMN, 0);
        lv_obj_set_size(rin, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
        microLabel(rin, "RESETS IN", COL_FAINT);
        char rbuf[16]; fmtResetsIn(a.fhSec, rbuf, sizeof(rbuf));
        lv_obj_t* rv = line(rin, rbuf, COL_TEXT, F16);
        if (i < MAX_ACCOUNTS) s_resetLbl[i] = rv;   // live-tick handle

        lv_obj_t* rnw = flexBox(foot, LV_FLEX_FLOW_COLUMN, 0);
        lv_obj_set_size(rnw, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
        lv_obj_set_flex_align(rnw, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_END);
        microLabel(rnw, "RENEWS", COL_FAINT);
        rlabel(rnw, a.wkRenew.length() ? a.wkRenew.c_str() : "--", COL_TEXT, F16);
    }
}

// ----------------------------------------------------------------- cloudflare

static void fillCloudflare() {
    lv_obj_t* page = s_screen[SC_CLOUDFLARE];
    lv_obj_clean(page);
    lv_obj_set_flex_flow(page, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(page, 11, 0);
    lv_obj_set_style_pad_row(page, 10, 0);

    // Totals strip: 4 stat tiles.
    lv_obj_t* strip = flexBox(page, LV_FLEX_FLOW_ROW, 10);
    lv_obj_set_size(strip, lv_pct(100), LV_SIZE_CONTENT);
    char cbuf[8];
    if (s_data.cfTotals.cache >= 0) snprintf(cbuf, sizeof(cbuf), "%d%%", s_data.cfTotals.cache);
    else                            snprintf(cbuf, sizeof(cbuf), "--");
    statTile(strip, "Requests - today", s_data.cfTotals.req.c_str(), COL_TEXT);
    statTile(strip, "Bandwidth", s_data.cfTotals.bw.c_str(), COL_TEXT);
    statTile(strip, "Threats blocked", s_data.cfTotals.threats.c_str(), COL_AMBER);
    statTile(strip, "Cache hit ratio", cbuf, COL_GOOD);

    // Sites panel: header (SITES + count / pager), then 6 rows.
    lv_obj_t* panel = well(page, 14);
    lv_obj_set_width(panel, lv_pct(100));
    lv_obj_set_flex_grow(panel, 1);
    lv_obj_set_style_pad_all(panel, 12, 0);
    lv_obj_set_style_pad_row(panel, 4, 0);

    lv_obj_t* hdr = flexBox(panel, LV_FLEX_FLOW_ROW, 0);
    lv_obj_set_size(hdr, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_align(hdr, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    char shown[48];
    snprintf(shown, sizeof(shown), "SITES  %d shown", (int)s_data.sites.size());
    microLabel(hdr, shown, COL_MUTED);

    // Pager.
    int total = (int)s_data.sites.size();
    int last = total ? (total - 1) / SITES_PER_PAGE : 0;
    if (s_cfPage > last) s_cfPage = last;
    lv_obj_t* pager = flexBox(hdr, LV_FLEX_FLOW_ROW, 8);
    lv_obj_set_size(pager, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_set_flex_align(pager, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    auto pagerBtn = [&](const char* glyph, lv_event_cb_t cb, bool enabled) {
        lv_obj_t* b = lv_obj_create(pager);
        lv_obj_set_size(b, 44, 34);
        lv_obj_set_style_bg_color(b, COL_TILE, 0);
        lv_obj_set_style_bg_opa(b, LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(b, 0, 0);
        lv_obj_set_style_radius(b, 8, 0);
        lv_obj_set_style_pad_all(b, 0, 0);
        lv_obj_clear_flag(b, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_t* g = line(b, glyph, enabled ? COL_ACCENT : COL_FAINT, F20);
        lv_obj_center(g);
        if (enabled) {
            lv_obj_add_flag(b, LV_OBJ_FLAG_CLICKABLE);
            lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, nullptr);
        }
    };
    pagerBtn("<", onPagerPrev, s_cfPage > 0);
    char pl[12]; snprintf(pl, sizeof(pl), "%d / %d", s_cfPage + 1, last + 1);
    line(pager, pl, COL_TEXT, F14);
    pagerBtn(">", onPagerNext, s_cfPage < last);

    // Site rows for this page.
    lv_obj_t* list = flexBox(panel, LV_FLEX_FLOW_COLUMN, 0);
    lv_obj_set_size(list, lv_pct(100), lv_pct(100));
    lv_obj_set_flex_grow(list, 1);
    lv_obj_clear_flag(list, LV_OBJ_FLAG_SCROLLABLE);

    if (s_data.sites.empty()) {
        lv_obj_center(line(list, "NO CLOUDFLARE SITES", COL_MUTED));
        return;
    }

    int start = s_cfPage * SITES_PER_PAGE;
    int end = start + SITES_PER_PAGE;
    if (end > total) end = total;
    for (int i = start; i < end; i++) {
        const SiteRow& z = s_data.sites[i];
        lv_obj_t* r = flexBox(list, LV_FLEX_FLOW_ROW, 8);
        lv_obj_set_size(r, lv_pct(100), 56);
        lv_obj_set_flex_align(r, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
        lv_obj_set_style_border_color(r, COL_DIV, 0);
        lv_obj_set_style_border_side(r, LV_BORDER_SIDE_BOTTOM, 0);
        lv_obj_set_style_border_width(r, 1, 0);

        dot(r, statusColor(z.st), 10);
        lv_obj_t* dom = line(r, z.dom.c_str(), COL_TEXT, F16);
        lv_obj_set_flex_grow(dom, 1);
        lv_label_set_long_mode(dom, LV_LABEL_LONG_DOT);
        lv_obj_set_width(dom, 100);

        lv_obj_t* req = rlabel(r, z.req.length() ? z.req.c_str() : "—", COL_TEXT, F16);
        lv_obj_set_width(req, 86);
        lv_obj_t* bw = rlabel(r, z.bw.length() ? z.bw.c_str() : "", COL_MUTED, F14);
        lv_obj_set_width(bw, 66);

        lv_obj_t* spk = flexBox(r, LV_FLEX_FLOW_COLUMN, 0);
        lv_obj_set_size(spk, 74, 24);
        sparkline(spk, z.spark, statusColor(z.st), 24, LV_OPA_COVER);

        lv_obj_t* stx = rlabel(r, statusText(z.st), statusColor(z.st), F14);
        lv_obj_set_width(stx, 92);
    }
}

static void rebuildCloudflare() { fillCloudflare(); applyChrome(); }

// ----------------------------------------------------------------- paddle

static void fillPaddle() {
    lv_obj_t* page = s_screen[SC_PADDLE];
    lv_obj_clean(page);
    lv_obj_set_flex_flow(page, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(page, 11, 0);
    lv_obj_set_style_pad_row(page, 10, 0);

    // Totals strip: revenue today, revenue month, combined sales/customers + MoM.
    lv_obj_t* strip = flexBox(page, LV_FLEX_FLOW_ROW, 10);
    lv_obj_set_size(strip, lv_pct(100), LV_SIZE_CONTENT);
    statTile(strip, "Revenue - today", s_data.paddleTotals.revToday.c_str(), COL_GOOD);
    statTile(strip, "Revenue - month", s_data.paddleTotals.revMonth.c_str(), COL_TEXT);
    // Combined tile: "<sales> sales -<custs> customers" / "+12% MoM".
    {
        lv_obj_t* t = well(strip, 12);
        lv_obj_set_style_pad_all(t, 12, 0);
        lv_obj_set_style_pad_row(t, 4, 0);
        lv_obj_set_flex_grow(t, 1);
        char cap[64];
        snprintf(cap, sizeof(cap), "%s sales - %s customers",
                 s_data.paddleTotals.sales.length() ? s_data.paddleTotals.sales.c_str() : "--",
                 s_data.paddleTotals.custs.length() ? s_data.paddleTotals.custs.c_str() : "--");
        microLabel(t, cap, COL_MUTED);
        char mom[32];
        snprintf(mom, sizeof(mom), "%s MoM",
                 s_data.paddleTotals.mom.length() ? s_data.paddleTotals.mom.c_str() : "0%");
        line(t, mom, COL_GOOD, F20);
    }

    if (s_data.products.empty()) {
        lv_obj_t* ph = flexBox(page, LV_FLEX_FLOW_COLUMN, 0);
        lv_obj_set_size(ph, lv_pct(100), lv_pct(100));
        lv_obj_set_flex_grow(ph, 1);
        lv_obj_center(line(ph, "NO PADDLE PRODUCTS", COL_MUTED));
        return;
    }

    // 2x2 product grid.
    lv_obj_t* gridwrap = flexBox(page, LV_FLEX_FLOW_COLUMN, 10);
    lv_obj_set_width(gridwrap, lv_pct(100));
    lv_obj_set_flex_grow(gridwrap, 1);

    lv_obj_t* rows[2];
    rows[0] = flexBox(gridwrap, LV_FLEX_FLOW_ROW, 10);
    rows[1] = flexBox(gridwrap, LV_FLEX_FLOW_ROW, 10);
    for (int i = 0; i < 2; i++) {
        lv_obj_set_width(rows[i], lv_pct(100));
        lv_obj_set_flex_grow(rows[i], 1);
    }

    for (size_t i = 0; i < s_data.products.size(); i++) {
        const ProductRow& p = s_data.products[i];
        lv_obj_t* c = card(rows[i / 2], 14);
        lv_obj_set_flex_grow(c, 1);
        lv_obj_set_height(c, lv_pct(100));
        lv_obj_set_style_pad_row(c, 6, 0);

        line(c, p.name.c_str(), COL_TEXT, F20);
        char sub[48];
        snprintf(sub, sizeof(sub), "macOS - %s", p.cat.length() ? p.cat.c_str() : "App");
        line(c, sub, COL_FAINT, F14);

        // Three mini-stats.
        lv_obj_t* mini = flexBox(c, LV_FLEX_FLOW_ROW, 18);
        lv_obj_set_size(mini, lv_pct(100), LV_SIZE_CONTENT);
        auto ministat = [&](const char* cap, const char* val, lv_color_t vc) {
            lv_obj_t* col = flexBox(mini, LV_FLEX_FLOW_COLUMN, 1);
            lv_obj_set_size(col, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
            microLabel(col, cap, COL_FAINT);
            line(col, val && val[0] ? val : "--", vc, F16);
        };
        ministat("PURCHASES", p.buys.c_str(), COL_TEXT);
        ministat("CUSTOMERS", p.custs.c_str(), COL_TEXT);
        ministat("REVENUE", p.rev.c_str(), COL_GOOD);

        lv_obj_t* spacer = flexBox(c, LV_FLEX_FLOW_COLUMN, 0);
        lv_obj_set_flex_grow(spacer, 1);
        lv_obj_set_width(spacer, lv_pct(100));
        sparkline(c, p.spark, COL_GOOD, 26, LV_OPA_50);
    }
}

// ----------------------------------------------------------------- github

static void fillGithub() {
    lv_obj_t* page = s_screen[SC_GITHUB];
    lv_obj_clean(page);
    lv_obj_set_flex_flow(page, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(page, 11, 0);
    lv_obj_set_style_pad_row(page, 10, 0);

    // Summary strip: repos / open issues / open PRs.
    lv_obj_t* strip = flexBox(page, LV_FLEX_FLOW_ROW, 10);
    lv_obj_set_size(strip, lv_pct(100), LV_SIZE_CONTENT);
    char rbuf[8]; snprintf(rbuf, sizeof(rbuf), "%d", s_data.ghSummary.repos);
    statTile(strip, "Repositories", rbuf, COL_TEXT);
    statTile(strip, "Open issues", s_data.ghSummary.issues.c_str(), COL_AMBER);
    statTile(strip, "Open PRs", s_data.ghSummary.prs.c_str(), COL_BLUE);

    // Repo list.
    lv_obj_t* panel = well(page, 14);
    lv_obj_set_width(panel, lv_pct(100));
    lv_obj_set_flex_grow(panel, 1);
    lv_obj_set_style_pad_all(panel, 12, 0);
    lv_obj_set_style_pad_row(panel, 0, 0);
    lv_obj_add_flag(panel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scroll_dir(panel, LV_DIR_VER);

    if (s_data.repos.empty()) {
        lv_obj_center(line(panel, "NO GITHUB REPOS", COL_MUTED));
        return;
    }

    for (const RepoRow& r : s_data.repos) {
        lv_obj_t* row = flexBox(panel, LV_FLEX_FLOW_ROW, 8);
        lv_obj_set_size(row, lv_pct(100), 57);
        lv_obj_set_flex_align(row, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
        lv_obj_set_style_border_color(row, COL_DIV, 0);
        lv_obj_set_style_border_side(row, LV_BORDER_SIDE_BOTTOM, 0);
        lv_obj_set_style_border_width(row, 1, 0);

        // Left cell: lang dot + name over "owner - lang".
        lv_color_t lcol = COL_MUTED;
        if (r.lcol.length() == 7 && r.lcol[0] == '#') {
            long v = strtol(r.lcol.c_str() + 1, nullptr, 16);
            lcol = lv_color_hex((uint32_t)v);
        }
        dot(row, lcol, 10);
        lv_obj_t* left = flexBox(row, LV_FLEX_FLOW_COLUMN, 1);
        lv_obj_set_flex_grow(left, 1);
        lv_obj_set_height(left, LV_SIZE_CONTENT);
        line(left, r.name.c_str(), COL_TEXT, F16);
        char meta[64];
        snprintf(meta, sizeof(meta), "%s - %s",
                 r.owner.length() ? r.owner.c_str() : "?",
                 r.lang.length() ? r.lang.c_str() : "—");
        line(left, meta, COL_FAINT, F14);

        char sbuf[16];
        snprintf(sbuf, sizeof(sbuf), "* %s", r.stars.length() ? r.stars.c_str() : "0");
        lv_obj_t* st = rlabel(row, sbuf, COL_AMBER, F14);
        lv_obj_set_width(st, 66);
        char ibuf[16]; snprintf(ibuf, sizeof(ibuf), "%s issues", r.issues.length() ? r.issues.c_str() : "0");
        lv_obj_t* is = rlabel(row, ibuf, COL_TEXT, F14);
        lv_obj_set_width(is, 82);
        char pbuf[12]; snprintf(pbuf, sizeof(pbuf), "%s PR", r.prs.length() ? r.prs.c_str() : "0");
        lv_obj_t* pr = rlabel(row, pbuf, COL_BLUE, F14);
        lv_obj_set_width(pr, 56);
        lv_obj_t* pu = rlabel(row, r.push.length() ? r.push.c_str() : "", COL_FAINT, F14);
        lv_obj_set_width(pu, 40);
    }
}

// ----------------------------------------------------------------- public API

void ui_init() {
    lv_obj_t* scr = lv_scr_act();
    lv_obj_set_style_bg_color(scr, COL_BG, 0);
    lv_obj_set_flex_flow(scr, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(scr, 0, 0);
    lv_obj_set_style_pad_row(scr, 0, 0);
    lv_obj_clear_flag(scr, LV_OBJ_FLAG_SCROLLABLE);

    buildHeaders(scr);

    // Screen stack: five full-size containers sharing one cell; one visible.
    lv_obj_t* stack = lv_obj_create(scr);
    lv_obj_set_width(stack, lv_pct(100));
    lv_obj_set_flex_grow(stack, 1);
    lv_obj_set_style_bg_opa(stack, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(stack, 0, 0);
    lv_obj_set_style_pad_all(stack, 0, 0);
    lv_obj_clear_flag(stack, LV_OBJ_FLAG_SCROLLABLE);
    for (int i = 0; i < SC_COUNT; i++) {
        s_screen[i] = lv_obj_create(stack);
        lv_obj_set_size(s_screen[i], lv_pct(100), lv_pct(100));
        lv_obj_align(s_screen[i], LV_ALIGN_TOP_LEFT, 0, 0);
        lv_obj_set_style_bg_opa(s_screen[i], LV_OPA_TRANSP, 0);
        lv_obj_set_style_border_width(s_screen[i], 0, 0);
        lv_obj_set_style_pad_all(s_screen[i], 0, 0);
        lv_obj_clear_flag(s_screen[i], LV_OBJ_FLAG_SCROLLABLE);
        if (i != SC_HOME) lv_obj_add_flag(s_screen[i], LV_OBJ_FLAG_HIDDEN);
    }
    lv_obj_center(line(s_screen[SC_HOME], "WAITING FOR HOST", COL_MUTED));

    // STALE banner overlay (top layer, above content).
    s_stale = lv_label_create(lv_layer_top());
    lv_label_set_text(s_stale, "STALE - no update in 10 min");
    lv_obj_set_style_text_color(s_stale, COL_CRIT, 0);
    lv_obj_set_style_text_font(s_stale, F16, 0);
    lv_obj_set_style_bg_color(s_stale, COL_BG, 0);
    lv_obj_set_style_bg_opa(s_stale, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_all(s_stale, 6, 0);
    lv_obj_set_style_radius(s_stale, 6, 0);
    lv_obj_align(s_stale, LV_ALIGN_TOP_MID, 0, 4);
    lv_obj_add_flag(s_stale, LV_OBJ_FLAG_HIDDEN);

    // Brightness dim overlay (top layer, pointer-events transparent).
    s_dim = lv_obj_create(lv_layer_top());
    lv_obj_set_size(s_dim, lv_pct(100), lv_pct(100));
    lv_obj_set_style_bg_color(s_dim, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(s_dim, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(s_dim, 0, 0);
    lv_obj_set_style_radius(s_dim, 0, 0);
    lv_obj_clear_flag(s_dim, LV_OBJ_FLAG_CLICKABLE);
    // Hidden by default (brightness 100 = no dim). A full-screen top-layer object
    // forces the compositor to touch every pixel each refresh, which aggravates
    // the RGB panel's PSRAM-bandwidth jitter — so keep it out of the tree until
    // brightness is actually turned down (Phase 3 admin).
    lv_obj_add_flag(s_dim, LV_OBJ_FLAG_FLOATING | LV_OBJ_FLAG_HIDDEN);

    applyChrome();
}

void ui_update(const Dashboard& d) {
    if (!d.valid) return;
    s_data = d;
    s_haveData = true;

    // Seed the live-tick counters from the fresh payload.
    s_clock = d.base;
    for (size_t i = 0; i < MAX_ACCOUNTS; i++)
        s_fhSec[i] = (i < d.accounts.size()) ? d.accounts[i].fhSec : -1;

    // Header clock/date (built once in the chrome, updated in place).
    char cbuf[8]; fmtClock(s_clock, cbuf, sizeof(cbuf));
    lv_label_set_text(s_homeClock, cbuf);
    lv_label_set_text(s_pageClock, cbuf);
    lv_label_set_text(s_homeDate, d.date.length() ? d.date.c_str() : "");

    // New data invalidates every screen. Rebuild only the visible one now; the
    // rest rebuild lazily when navigated to, so LVGL's heap only ever holds one
    // screen's objects (building all five at once overflows it and crashes).
    for (int i = 0; i < SC_COUNT; i++) s_dirty[i] = true;
    showScreen(s_active);
}

void ui_tick_1hz() {
    if (!s_haveData || !s_live) return;

    // Advance the header clock.
    if (s_clock >= 0) {
        s_clock = (s_clock + 1) % 86400;
        char cbuf[8]; fmtClock(s_clock, cbuf, sizeof(cbuf));
        if (s_homeClock) lv_label_set_text(s_homeClock, cbuf);
        if (s_pageClock) lv_label_set_text(s_pageClock, cbuf);
    }

    // Count each account's RESETS-IN down (mutate the label only).
    for (size_t i = 0; i < MAX_ACCOUNTS; i++) {
        if (!s_resetLbl[i]) continue;
        if (s_fhSec[i] > 0) s_fhSec[i]--;
        char rbuf[16]; fmtResetsIn(s_fhSec[i], rbuf, sizeof(rbuf));
        lv_label_set_text(s_resetLbl[i], rbuf);
    }
}

void ui_set_live(bool live) {
    s_live = live;
    if (s_hdrPage) applyChrome();
}

void ui_set_stale(bool stale) {
    if (!s_stale) return;
    if (stale) lv_obj_clear_flag(s_stale, LV_OBJ_FLAG_HIDDEN);
    else       lv_obj_add_flag(s_stale, LV_OBJ_FLAG_HIDDEN);
}

void ui_set_wifi(bool connected) {
    // Show the header WiFi bars only while associated. The icon is a FLOATING
    // overlay, so toggling HIDDEN doesn't disturb the header's flex layout.
    // Guarded so the 1 Hz caller only acts on a real state change.
    int state = connected ? 1 : 0;
    if (state == s_wifiState) return;
    s_wifiState = state;
    for (lv_obj_t* icon : {s_wifiHome, s_wifiPage}) {
        if (!icon) continue;
        if (connected) lv_obj_clear_flag(icon, LV_OBJ_FLAG_HIDDEN);
        else           lv_obj_add_flag(icon, LV_OBJ_FLAG_HIDDEN);
    }
}

void ui_set_brightness(uint8_t pct) {
    if (!s_dim) return;
    if (pct > 100) pct = 100;
    if (pct >= 100) {                       // no dim — drop the overlay entirely
        lv_obj_add_flag(s_dim, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    lv_obj_clear_flag(s_dim, LV_OBJ_FLAG_HIDDEN);
    // opacity = (100 - brightness)/100 * 0.5  (max half-black at brightness 0).
    lv_opa_t opa = (lv_opa_t)((100 - pct) * 255 / 100 / 2);
    lv_obj_set_style_bg_opa(s_dim, opa, 0);
}
