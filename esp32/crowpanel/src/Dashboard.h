// Cockpit data model — the parsed `set_cockpit` payload.
//
// Deliberately dumb value holders: the host formats every string (counts like
// "1.2M", countdowns like "1H02M", money like "$1,248"); the device only stores
// and draws them, plus bars/sparklines/histograms from the integer fields. The
// two exceptions are the sanctioned live-tick numerics — `base` (seconds since
// local midnight, the header-clock seed) and each account's `fhSec` (seconds to
// the 5h reset) — which the device increments/decrements 1/s between pushes
// (see ../../docs/protocol.md live-tick note).
//
// Nothing here is persisted — after a reboot the panel shows its boot screen
// until the host pushes again. This struct is populated ONLY by Protocol::handle
// and read ONLY by ui_update(), so a later on-device fetcher (Phase 4) can fill
// the same shape without touching the UI.
#pragma once

#include <Arduino.h>
#include <vector>

// Payload caps — mirror the host's (see host/src/claudemon/render.py).
static const size_t MAX_ACCOUNTS = 3;    // Anthropic account cards
static const size_t MAX_SITES    = 12;   // Cloudflare sites (paginated 6/page)
static const size_t MAX_PRODUCTS = 4;    // Paddle product grid (2x2)
static const size_t MAX_REPOS    = 6;    // GitHub repo rows
static const size_t MAX_ALERTS   = 8;    // derived alerts
static const size_t ACT_BUCKETS  = 24;   // messages/hour histogram
static const size_t MAX_SPARK    = 32;   // sparkline point clamp

// Per-row source health, mirrors the host's `st` field. 'o' ok, 'a' auth,
// 'e' err, 'd' drift. Site rows reuse this with 'o'=up, plus 'g' degraded,
// 'x' down (mapped from the "up"/"degraded"/"down" strings).
static inline char statusChar(const char* st) {
    if (!st || !st[0]) return 'o';
    // Cloudflare site states arrive as words; map to single chars.
    if (strcmp(st, "up") == 0)       return 'o';
    if (strcmp(st, "degraded") == 0) return 'g';
    if (strcmp(st, "down") == 0)     return 'x';
    return st[0];   // ok/auth/err/drift -> first char
}

struct AccountRow {
    String label;             // "WORK"
    int8_t fhPct = -1;        // 5-hour utilization 0-100, -1 unknown
    String fhReset;           // host-rendered "1H02M" (fallback string)
    int32_t fhSec = -1;       // seconds to 5h reset, device counts down; -1 unknown
    int8_t wkPct = -1;        // weekly utilization 0-100, -1 unknown
    String wkRenew;           // "WED 8PM (3D)"
    String plan;              // "Max 20×"
    String msgs;              // pre-formatted "412"
    std::vector<uint8_t> act; // 24-bucket messages/hour histogram, each 0-100
    char   st = 'o';
};

struct CfTotals {
    String req;               // "4.28M"
    String bw;                // "312GB"
    String threats;           // "18.4K"
    int8_t cache = -1;        // cache-hit % 0-100, -1 unknown
};

struct SiteRow {
    String dom;               // "blog.wizemann.com"
    String req;               // "350K"
    String bw;                // "1.3GB"
    std::vector<uint8_t> spark;   // request trend, each 0-100
    char   st = 'o';          // 'o' up | 'g' degraded | 'x' down
};

struct PaddleTotals {
    String revToday;          // "$1,248"
    String revMonth;          // "$98,720"
    String sales;             // "5.1K"
    String custs;             // "15K"
    String mom;               // "+12%"
};

struct ProductRow {
    String name;              // "PixelPeek"
    String cat;               // "Utilities"
    String buys;              // "1.3K"
    String custs;             // "4.1K"
    String rev;               // "$38,540"
    std::vector<uint8_t> spark;   // revenue trend, each 0-100
    char   st = 'o';
};

struct GhSummary {
    int    repos = 0;
    String issues;            // "96"
    String prs;               // "18"
};

struct RepoRow {
    String name;              // "claudemon"
    String owner;             // "awizemann"
    String lang;              // "C++"
    String lcol;              // language-dot hex hint "#8FBF7F" or ""
    String stars;             // "342"
    String issues;            // "12"
    String prs;               // "3"
    String push;              // "2h"
    char   st = 'o';
};

struct AlertRow {
    int8_t lvl = 2;           // 0 critical, 1 warning, 2 info
    String tag;               // "CRITICAL" / "WARNING" / "INFO"
    String time;              // relative age, "now" / "3m"
    String msg;               // host-rendered message
    String src;               // "Cloudflare" / "Anthropic" / "GitHub"
};

struct Dashboard {
    String updated;           // "14:32" host clock (fallback when not ticking)
    int32_t base = -1;        // seconds since local midnight; device ticks it up
    String date;              // "Sun 12 Jul"

    std::vector<AccountRow> accounts;

    CfTotals              cfTotals;
    int                   cfDown = 0;
    int                   cfDegraded = 0;
    std::vector<SiteRow>  sites;

    PaddleTotals            paddleTotals;
    std::vector<ProductRow> products;

    GhSummary            ghSummary;
    std::vector<RepoRow> repos;

    std::vector<AlertRow> alerts;

    bool valid = false;       // false until the first set_cockpit arrives
};
