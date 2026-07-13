#include "Protocol.h"
#include <ArduinoJson.h>

// Clamp a JSON int to 0-100 (for the *_pct / cache fields the device bars).
static int8_t pct100(JsonVariantConst v, int dflt = -1) {
    if (v.isNull()) return (int8_t)dflt;
    int p = v.as<int>();
    return (int8_t)(p < 0 ? -1 : (p > 100 ? 100 : p));
}

// Parse a normalized 0-100 series (sparkline / activity histogram) into `out`,
// clamping each point and the total count.
static void parseSeries(JsonArrayConst arr, std::vector<uint8_t>& out, size_t cap) {
    for (JsonVariantConst v : arr) {
        if (out.size() >= cap) break;
        int p = v.as<int>();
        out.push_back((uint8_t)(p < 0 ? 0 : (p > 100 ? 100 : p)));
    }
}

String Protocol::handle(const String& line, Dashboard& out, bool& dashboardUpdated) {
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, line);
    if (err) {
        return makeError("invalid JSON");
    }

    const char* cmd = doc["cmd"];
    if (cmd == nullptr) {
        return makeError("missing 'cmd' field");
    }

    JsonObjectConst params = doc["params"].as<JsonObjectConst>();
    if (params.isNull()) {
        params = doc.as<JsonObjectConst>();
    }

    if (strcmp(cmd, "ping") == 0) {
        return makeOk("pong", nullptr);
    }
    if (strcmp(cmd, "set_cockpit") == 0) {
        String reply = parseCockpit(params, out);
        dashboardUpdated = out.valid;   // only render if the parse populated data
        return reply;
    }
    return makeError("unknown command");
}

String Protocol::parseCockpit(const JsonObjectConst& params, Dashboard& out) {
    // Rebuild from scratch each push (ephemeral, no merge).
    Dashboard next;
    next.updated = params["updated"] | "";
    next.base    = params["base"] | -1;
    next.date    = params["date"] | "";

    // ---- Anthropic accounts ----
    for (JsonObjectConst a : params["anthropic"]["accounts"].as<JsonArrayConst>()) {
        if (next.accounts.size() >= MAX_ACCOUNTS) break;
        AccountRow r;
        r.label   = a["label"]  | "?";
        r.fhPct   = pct100(a["fh_pct"]);
        r.fhReset = a["fh_rst"] | "";
        r.fhSec   = a["fh_sec"] | -1;
        r.wkPct   = pct100(a["wk_pct"]);
        r.wkRenew = a["wk_rnw"] | "";
        r.wsPct   = pct100(a["ws_pct"]);
        r.sev     = a["sev"]    | "";
        r.cred    = a["cred"]   | "";
        r.actv    = a["actv"]   | "";
        r.st      = statusChar(a["st"] | "ok");
        next.accounts.push_back(r);
    }

    // ---- Cloudflare ----
    JsonObjectConst cf = params["cloudflare"].as<JsonObjectConst>();
    if (!cf.isNull()) {
        JsonObjectConst t = cf["totals"].as<JsonObjectConst>();
        next.cfTotals.req     = t["req"]     | "";
        next.cfTotals.bw      = t["bw"]      | "";
        next.cfTotals.threats = t["threats"] | "";
        next.cfTotals.cache   = pct100(t["cache"]);
        next.cfDown     = cf["down"]     | 0;
        next.cfDegraded = cf["degraded"] | 0;
        for (JsonObjectConst z : cf["sites"].as<JsonArrayConst>()) {
            if (next.sites.size() >= MAX_SITES) break;
            SiteRow s;
            s.dom = z["dom"] | "?";
            s.req = z["req"] | "";
            s.bw  = z["bw"]  | "";
            parseSeries(z["spark"].as<JsonArrayConst>(), s.spark, MAX_SPARK);
            s.st  = statusChar(z["st"] | "up");
            next.sites.push_back(s);
        }
    }

    // ---- Paddle ----
    JsonObjectConst pd = params["paddle"].as<JsonObjectConst>();
    if (!pd.isNull()) {
        JsonObjectConst t = pd["totals"].as<JsonObjectConst>();
        next.paddleTotals.revToday = t["rev_today"] | "";
        next.paddleTotals.revMonth = t["rev_month"] | "";
        next.paddleTotals.sales    = t["sales"]     | "";
        next.paddleTotals.custs    = t["custs"]     | "";
        next.paddleTotals.mom      = t["mom"]       | "";
        for (JsonObjectConst p : pd["products"].as<JsonArrayConst>()) {
            if (next.products.size() >= MAX_PRODUCTS) break;
            ProductRow r;
            r.name  = p["name"]  | "?";
            r.cat   = p["cat"]   | "";
            r.buys  = p["buys"]  | "";
            r.custs = p["custs"] | "";
            r.rev   = p["rev"]   | "";
            parseSeries(p["spark"].as<JsonArrayConst>(), r.spark, MAX_SPARK);
            r.st    = statusChar(p["st"] | "ok");
            next.products.push_back(r);
        }
    }

    // ---- GitHub ----
    JsonObjectConst gh = params["github"].as<JsonObjectConst>();
    if (!gh.isNull()) {
        JsonObjectConst s = gh["summary"].as<JsonObjectConst>();
        next.ghSummary.repos  = s["repos"]  | 0;
        next.ghSummary.issues = s["issues"] | "";
        next.ghSummary.prs    = s["prs"]    | "";
        for (JsonObjectConst g : gh["repos"].as<JsonArrayConst>()) {
            if (next.repos.size() >= MAX_REPOS) break;
            RepoRow r;
            r.name   = g["name"]   | "?";
            r.owner  = g["owner"]  | "";
            r.lang   = g["lang"]   | "";
            r.lcol   = g["lcol"]   | "";
            r.stars  = g["stars"]  | "";
            r.issues = g["issues"] | "";
            r.prs    = g["prs"]    | "";
            r.push   = g["push"]   | "";
            r.st     = statusChar(g["st"] | "ok");
            next.repos.push_back(r);
        }
    }

    // ---- Alerts ----
    for (JsonObjectConst a : params["alerts"].as<JsonArrayConst>()) {
        if (next.alerts.size() >= MAX_ALERTS) break;
        AlertRow r;
        r.lvl  = (int8_t)(a["lvl"] | 2);
        r.tag  = a["tag"]  | "";
        r.time = a["time"] | "";
        r.msg  = a["msg"]  | "";
        r.src  = a["src"]  | "";
        next.alerts.push_back(r);
    }

    // A payload with no sections at all is almost certainly a truncated line —
    // reject it rather than blanking the screen.
    if (next.accounts.empty() && next.sites.empty() &&
        next.products.empty() && next.repos.empty() && next.alerts.empty()) {
        return makeError("set_cockpit had no rows (truncated line?)");
    }

    next.valid = true;
    out = next;
    return makeOk("set_cockpit", "cockpit updated");
}

String Protocol::makeOk(const char* cmd, const char* msg) {
    JsonDocument doc;
    doc["status"] = "ok";
    doc["cmd"]    = cmd;
    if (msg) doc["msg"] = msg;
    String out;
    serializeJson(doc, out);
    return out;
}

String Protocol::makeError(const char* msg) {
    JsonDocument doc;
    doc["status"] = "error";
    doc["msg"]    = msg;
    String out;
    serializeJson(doc, out);
    return out;
}
