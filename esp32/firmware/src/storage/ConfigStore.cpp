#include "ConfigStore.h"

static const char* NVS_NAMESPACE = "epaper_cfg";

ConfigStore::ConfigStore()
{
}

void ConfigStore::init()
{
    Serial.println("[Config] NVS storage initialized");
}

void ConfigStore::saveWiFi(const String& ssid, const String& password)
{
    _prefs.begin(NVS_NAMESPACE, false);
    _prefs.putString("wifi_ssid", ssid);
    _prefs.putString("wifi_pass", password);
    _prefs.end();
    Serial.printf("[Config] WiFi saved: %s\n", ssid.c_str());
}

void ConfigStore::loadWiFi(String& ssid, String& password)
{
    _prefs.begin(NVS_NAMESPACE, true);
    ssid = _prefs.getString("wifi_ssid", "");
    password = _prefs.getString("wifi_pass", "");
    _prefs.end();
}

bool ConfigStore::hasWiFiConfig()
{
    _prefs.begin(NVS_NAMESPACE, true);
    bool has = _prefs.isKey("wifi_ssid") && _prefs.getString("wifi_ssid", "").length() > 0;
    _prefs.end();
    return has;
}

void ConfigStore::saveAudio(bool enabled, int volume)
{
    _prefs.begin(NVS_NAMESPACE, false);
    _prefs.putBool("audio_en", enabled);
    _prefs.putInt("audio_vol", volume);
    _prefs.end();
    Serial.printf("[Config] Audio saved: %s, vol=%d\n", enabled ? "on" : "off", volume);
}

void ConfigStore::loadAudio(bool& enabled, int& volume)
{
    _prefs.begin(NVS_NAMESPACE, true);
    enabled = _prefs.getBool("audio_en", false);
    volume = _prefs.getInt("audio_vol", 50);
    _prefs.end();
}

void ConfigStore::saveLayout(const String& layoutJson)
{
    _prefs.begin(NVS_NAMESPACE, false);
    _prefs.putString("layout", layoutJson);
    _prefs.end();
    Serial.println("[Config] Layout saved");
}

String ConfigStore::loadLayout()
{
    _prefs.begin(NVS_NAMESPACE, true);
    String json = _prefs.getString("layout", "");
    _prefs.end();
    return json;
}

void ConfigStore::saveAPIEndpoints(const std::vector<APIEndpointConfig>& endpoints)
{
    JsonDocument doc;
    JsonArray arr = doc.to<JsonArray>();

    for (const auto& ep : endpoints) {
        JsonObject obj = arr.add<JsonObject>();
        obj["name"] = ep.name;
        obj["url"] = ep.url;
        obj["authToken"] = ep.authToken;
        obj["interval"] = ep.intervalSec;
        obj["enabled"] = ep.enabled;

        JsonObject paths = obj["jsonPaths"].to<JsonObject>();
        for (const auto& p : ep.jsonPaths) {
            paths[p.first] = p.second;
        }
    }

    String json;
    serializeJson(doc, json);

    _prefs.begin(NVS_NAMESPACE, false);
    _prefs.putString("api_eps", json);
    _prefs.end();
    Serial.printf("[Config] %d API endpoint(s) saved\n", endpoints.size());
}

std::vector<APIEndpointConfig> ConfigStore::loadAPIEndpoints()
{
    std::vector<APIEndpointConfig> result;

    _prefs.begin(NVS_NAMESPACE, true);
    String json = _prefs.getString("api_eps", "");
    _prefs.end();

    if (json.length() == 0) return result;

    JsonDocument doc;
    if (deserializeJson(doc, json)) return result;

    JsonArray arr = doc.as<JsonArray>();
    for (JsonObject obj : arr) {
        APIEndpointConfig ep;
        ep.name = obj["name"].as<String>();
        ep.url = obj["url"].as<String>();
        ep.authToken = obj["authToken"].as<String>();
        ep.intervalSec = obj["interval"] | 60;
        ep.enabled = obj["enabled"] | false;

        JsonObject paths = obj["jsonPaths"];
        for (JsonPair p : paths) {
            ep.jsonPaths[String(p.key().c_str())] = p.value().as<String>();
        }

        result.push_back(ep);
    }

    return result;
}
