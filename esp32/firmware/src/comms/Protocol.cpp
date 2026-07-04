#include "Protocol.h"

Protocol::Protocol()
    : _wifi(nullptr)
    , _display(nullptr)
    , _audio(nullptr)
    , _api(nullptr)
    , _sensor(nullptr)
    , _config(nullptr)
{
}

void Protocol::init(WiFiManager* wifi, DisplayManager* display, AudioManager* audio,
                    APIPoller* api, SensorManager* sensor, ConfigStore* config)
{
    _wifi    = wifi;
    _display = display;
    _audio   = audio;
    _api     = api;
    _sensor  = sensor;
    _config  = config;
}

std::string Protocol::handleCommand(const std::string& input, const DeviceStatus& status)
{
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, input);

    if (err) {
        return makeError("invalid JSON");
    }

    const char* cmd = doc["cmd"];
    if (cmd == nullptr) {
        return makeError("missing 'cmd' field");
    }

    String command(cmd);
    JsonObjectConst params = doc["params"].as<JsonObjectConst>();

    // Also check top-level keys as params (macOS app sends flat JSON)
    if (params.isNull()) {
        params = doc.as<JsonObjectConst>();
    }

    if (command == "get_status") {
        return handleGetStatus(status);
    } else if (command == "ping") {
        return handlePing();
    } else if (command == "set_wifi") {
        return handleSetWifi(params);
    } else if (command == "set_layout") {
        return handleSetLayout(params);
    } else if (command == "set_usage") {
        return handleSetUsage(params);
    } else if (command == "set_api") {
        return handleSetApi(params);
    } else if (command == "set_audio") {
        return handleSetAudio(params);
    } else if (command == "get_config") {
        return handleGetConfig();
    }

    return makeError("unknown command");
}

std::string Protocol::handleGetStatus(const DeviceStatus& status)
{
    JsonDocument doc;
    doc["status"] = "ok";
    doc["cmd"]    = "get_status";

    JsonObject data       = doc["data"].to<JsonObject>();
    data["chip"]          = status.chipModel;
    data["mac"]           = status.macAddress;
    data["free_heap"]     = status.freeHeap;
    data["wifi"]          = status.wifiConnected;
    data["wifi_ssid"]     = status.wifiSSID;
    data["wifi_ip"]       = status.wifiIP;
    data["wifi_rssi"]     = status.wifiRSSI;
    data["ble"]           = status.bleConnected;
    data["fw_version"]    = status.firmwareVersion;
    data["temperature"]   = serialized(String(status.temperature, 1));
    data["humidity"]      = serialized(String(status.humidity, 1));
    data["audio_enabled"] = status.audioEnabled;
    data["audio_volume"]  = status.audioVolume;
    data["has_layout"]       = status.hasLayout;
    data["battery_percent"]  = status.batteryPercent;

    std::string out;
    serializeJson(doc, out);
    return out;
}

std::string Protocol::handlePing()
{
    JsonDocument doc;
    doc["status"] = "ok";
    doc["cmd"]    = "pong";

    std::string out;
    serializeJson(doc, out);
    return out;
}

std::string Protocol::handleSetWifi(JsonObjectConst params)
{
    const char* ssid = params["ssid"];
    if (ssid == nullptr) {
        return makeError("set_wifi requires 'ssid'");
    }

    const char* password = params["password"];
    String pass = password ? String(password) : "";

    // Save credentials to NVS first
    if (_config) {
        _config->saveWiFi(String(ssid), pass);
    }

    // Defer WiFi.begin() to the main loop — calling it from within
    // the NimBLE callback causes a stack overflow and reboot.
    if (_wifiConnectCb) {
        _wifiConnectCb(String(ssid), pass);
    }

    return makeOk("set_wifi", "WiFi credentials saved, connecting...");
}

std::string Protocol::handleSetLayout(JsonObjectConst params)
{
    if (!_display) {
        return makeError("display not available");
    }

    // The layout can come as a nested "layout" object or at the params level
    JsonObjectConst layoutObj = params["layout"].as<JsonObjectConst>();

    String layoutJson;
    if (!layoutObj.isNull()) {
        serializeJson(layoutObj, layoutJson);
    } else {
        // Try the whole params as layout
        serializeJson(params, layoutJson);
    }

    LayoutDef layout;
    if (!_display->parseLayoutJson(layoutJson, layout)) {
        return makeError("invalid layout JSON");
    }

    _display->setLayout(layout);

    if (_config) {
        _config->saveLayout(layoutJson);
    }

    // Trigger an immediate render with current data
    if (_api && _wifi) {
        _display->renderLayout(_api->getAllValues(), _wifi->isConnected(), true);
    }

    if (_audio && _audio->isEnabled()) {
        _audio->playSuccess();
    }

    return makeOk("set_layout", "layout applied");
}

std::string Protocol::handleSetUsage(JsonObjectConst params)
{
    if (!_display) {
        return makeError("display not available");
    }

    JsonArrayConst accounts = params["accounts"].as<JsonArrayConst>();
    if (accounts.isNull()) {
        return makeError("set_usage requires 'accounts' array");
    }

    // Ephemeral by design — not persisted to NVS. After a reboot the screen
    // shows the waiting message until the host pushes again.
    UsageData data;
    data.updatedAt = params["updated"] | "";

    for (JsonObjectConst acct : accounts) {
        if (data.accounts.size() >= 4) break;
        UsageAccount ua;
        ua.label         = acct["label"] | "?";
        ua.fiveHourPct   = (int8_t)(acct["fh_pct"] | -1);
        ua.fiveHourReset = acct["fh_rst"] | "";
        ua.weekPct       = (int8_t)(acct["wk_pct"] | -1);
        ua.weekRenewal   = acct["wk_rnw"] | "";
        const char* st   = acct["st"] | "o";
        ua.status        = st[0] ? st[0] : 'o';
        data.accounts.push_back(ua);
    }

    // Render is deferred to the main loop (setUsageData sets a pending flag):
    // the e-ink refresh blocks for seconds and the reply must go out first.
    _display->setUsageData(data);

    return makeOk("set_usage", "usage updated");
}

std::string Protocol::handleSetApi(JsonObjectConst params)
{
    if (!_api) {
        return makeError("API poller not available");
    }

    // Can be a single endpoint or nested under "api"
    JsonObjectConst apiObj = params["api"].as<JsonObjectConst>();
    if (apiObj.isNull()) {
        apiObj = params;
    }

    APIEndpointConfig ep;
    ep.name        = apiObj["name"] | "default";
    ep.url         = apiObj["url"] | "";
    ep.authToken   = apiObj["authToken"] | "";
    ep.intervalSec = apiObj["pollIntervalSeconds"] | 60;
    ep.enabled     = apiObj["enabled"] | true;

    if (ep.url.length() == 0) {
        return makeError("set_api requires 'url'");
    }

    // Parse jsonPaths
    JsonObjectConst paths = apiObj["jsonPaths"].as<JsonObjectConst>();
    if (!paths.isNull()) {
        for (JsonPairConst p : paths) {
            ep.jsonPaths[String(p.key().c_str())] = p.value().as<String>();
        }
    }

    _api->addEndpoint(ep);

    // Save all endpoints
    // Note: for simplicity, we rebuild the full list from the poller
    // In production you'd track separately
    if (_config) {
        std::vector<APIEndpointConfig> all;
        all.push_back(ep);
        _config->saveAPIEndpoints(all);
    }

    return makeOk("set_api", "API endpoint configured");
}

std::string Protocol::handleSetAudio(JsonObjectConst params)
{
    if (!_audio) {
        return makeError("audio not available");
    }

    if (params["enabled"].is<bool>()) {
        _audio->setEnabled(params["enabled"].as<bool>());
    }
    if (params["volume"].is<int>()) {
        _audio->setVolume(params["volume"].as<int>());
    }

    if (_config) {
        _config->saveAudio(_audio->isEnabled(), _audio->getVolume());
    }

    if (_audio->isEnabled()) {
        _audio->playNotification();
    }

    return makeOk("set_audio", "audio settings updated");
}

std::string Protocol::handleGetConfig()
{
    JsonDocument doc;
    doc["status"] = "ok";
    doc["cmd"]    = "get_config";

    JsonObject data = doc["data"].to<JsonObject>();

    if (_config) {
        String ssid, pass;
        _config->loadWiFi(ssid, pass);
        data["wifi_ssid"] = ssid;
        data["wifi_configured"] = ssid.length() > 0;

        bool audioEn;
        int audioVol;
        _config->loadAudio(audioEn, audioVol);
        data["audio_enabled"] = audioEn;
        data["audio_volume"]  = audioVol;

        String layoutJson = _config->loadLayout();
        data["has_layout"] = layoutJson.length() > 0;
    }

    std::string out;
    serializeJson(doc, out);
    return out;
}

std::string Protocol::makeError(const char* message)
{
    JsonDocument doc;
    doc["status"] = "error";
    doc["msg"]    = message;

    std::string out;
    serializeJson(doc, out);
    return out;
}

std::string Protocol::makeOk(const char* cmd, const char* msg)
{
    JsonDocument doc;
    doc["status"] = "ok";
    doc["cmd"]    = cmd;
    doc["msg"]    = msg;

    std::string out;
    serializeJson(doc, out);
    return out;
}
